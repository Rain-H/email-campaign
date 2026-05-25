#!/usr/bin/env python3
"""
CRM Database Operations

Shared module for all CRM read/write operations against PostgreSQL.
Used by send_postmark.py, crm_check.py, and other scripts.
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .db_config import get_connection


# Local-parts that indicate a placeholder/template rather than a real address.
# Compared by exact equality after lower-casing, so real prefixes like "anom"
# (which contains "nom") are NOT false-positive matches.
_PLACEHOLDER_LOCALS: frozenset = frozenset({
    "firstname", "lastname", "firstname.lastname",
    "prenom", "nom", "prenom.nom",
    "yourname", "your.email", "your_email",
    "name", "email",
    "noreply", "no-reply",
    "test", "dummy", "xxx",
})

# Domains that are obviously test/template placeholders.
_PLACEHOLDER_DOMAINS: frozenset = frozenset({
    "example.com", "example.org", "example.net",
    "test.com", "test.org", "tests.com",
    "dummy.com", "yourdomain.com", "domain.com",
})

# Minimal RFC-pragmatic email regex (covers virtually all real academic addrs).
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def is_valid_email(email: str) -> Tuple[bool, str]:
    """Return (is_valid, reason) for an email address.

    `reason` is an empty string when valid, otherwise a short human-readable
    explanation for logging/debugging.

    Designed to reject the failure modes we've observed in crawled data:
      - masked emails from EDAS (contain '*')
      - compound entries (whitespace, slash, comma, semicolon)
      - placeholder templates (`firstname.lastname@…`, `prenom.nom@…`)
      - obvious test/example domains
      - syntactically malformed addresses
    """
    if not email or not isinstance(email, str):
        return False, "empty or non-string"
    e = email.strip().lower()
    if "*" in e:
        return False, "contains masked characters (*)"
    if any(c in e for c in (" ", "\t", "/", ",", ";")):
        return False, "contains whitespace or separator"
    if e.count("@") != 1:
        return False, "must contain exactly one @"
    local, domain = e.split("@")
    if local in _PLACEHOLDER_LOCALS:
        return False, f"placeholder local-part: {local}"
    if domain in _PLACEHOLDER_DOMAINS:
        return False, f"placeholder domain: {domain}"
    if not _EMAIL_RE.match(e):
        return False, "fails basic email regex"
    return True, ""


def _parse_timestamp(ts_str: str) -> Optional[str]:
    """Parse various timestamp formats into a standard format for PostgreSQL."""
    if not ts_str:
        return None
    try:
        ts_clean = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_clean)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(ts_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


# ── Contact operations ──────────────────────────────────────────────

def upsert_contact(conn, email: str, name: str, conference: str,
                   source_platform: str = None) -> bool:
    """Insert or update a contact.

    Returns True if the row was upserted, False if the email failed validation
    and the row was skipped. A skip is logged so crawler runs surface the cause.
    """
    ok, reason = is_valid_email(email)
    if not ok:
        print(f"  [SKIP] invalid email '{email}' ({reason})")
        return False
    cur = conn.cursor()
    if source_platform:
        cur.execute("""
            INSERT INTO contacts (email, name, conference, source_platform)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(email) DO UPDATE SET
                name = EXCLUDED.name,
                conference = EXCLUDED.conference,
                source_platform = COALESCE(EXCLUDED.source_platform, contacts.source_platform)
        """, (email, name, conference, source_platform))
    else:
        cur.execute("""
            INSERT INTO contacts (email, name, conference)
            VALUES (%s, %s, %s)
            ON CONFLICT(email) DO UPDATE SET
                name = EXCLUDED.name,
                conference = EXCLUDED.conference
        """, (email, name, conference))
    cur.close()
    return True


# ── Email (send) operations ─────────────────────────────────────────

def insert_email(conn, contact_email: str, postmark_message_id: str,
                 subject: str, sent_at: str) -> Optional[int]:
    """Record a sent email. Returns the email row id."""
    cur = conn.cursor()
    ts = _parse_timestamp(sent_at) or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO emails (contact_email, postmark_message_id, subject, sent_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (postmark_message_id) DO NOTHING
        RETURNING id
    """, (contact_email, postmark_message_id, subject, ts))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


# ── Postmark status update operations ───────────────────────────────

def update_delivery(conn, postmark_message_id: str, delivered_at: str):
    cur = conn.cursor()
    cur.execute("""
        UPDATE emails SET delivered_at = %s
        WHERE postmark_message_id = %s AND delivered_at IS NULL
    """, (_parse_timestamp(delivered_at), postmark_message_id))
    cur.close()


def update_bounce(conn, postmark_message_id: str, bounced_at: str, bounce_type: str):
    cur = conn.cursor()
    cur.execute("""
        UPDATE emails SET bounced_at = %s, bounce_type = %s
        WHERE postmark_message_id = %s AND bounced_at IS NULL
    """, (_parse_timestamp(bounced_at), bounce_type, postmark_message_id))
    cur.close()


def update_open(conn, postmark_message_id: str, opened_at: str, open_count: int):
    cur = conn.cursor()
    cur.execute("""
        UPDATE emails
        SET opened_at = COALESCE(opened_at, %s),
            open_count = GREATEST(open_count, %s)
        WHERE postmark_message_id = %s
    """, (_parse_timestamp(opened_at), open_count, postmark_message_id))
    cur.close()


def update_click(conn, postmark_message_id: str, clicked_at: str):
    cur = conn.cursor()
    cur.execute("""
        UPDATE emails SET clicked_at = %s
        WHERE postmark_message_id = %s AND clicked_at IS NULL
    """, (_parse_timestamp(clicked_at), postmark_message_id))
    cur.close()


# ── Reply operations ────────────────────────────────────────────────

def insert_reply(conn, email_id: int, replied_at: str, content: str,
                 is_interested: bool) -> Optional[int]:
    """Record a reply. Skips if a reply already exists for this email_id."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM replies WHERE email_id = %s", (email_id,))
    if cur.fetchone():
        cur.close()
        return None
    ts = _parse_timestamp(replied_at) or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO replies (email_id, replied_at, full_content, is_interested)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """, (email_id, ts, content, is_interested))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def update_reply_classification(conn, email_id: int, is_interested: bool,
                                confidence: Optional[float] = None,
                                reasoning: Optional[str] = None):
    cur = conn.cursor()
    cur.execute("""
        UPDATE replies
        SET is_interested = %s,
            classification_confidence = %s,
            classification_reasoning = %s
        WHERE email_id = %s
    """, (is_interested, confidence, reasoning, email_id))
    cur.close()


# ── Conversation operations ────────────────────────────────────────

def insert_conversation(conn, contact_email: str, direction: str,
                        subject: str, body_text: str, message_at: str,
                        postmark_message_id: str = None,
                        body_html: str = None) -> Optional[int]:
    """Insert a conversation message. Returns the conversation id."""
    cur = conn.cursor()
    ts = _parse_timestamp(message_at) or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    # 计算 thread_order
    cur.execute("""
        SELECT COALESCE(MAX(thread_order), 0) + 1
        FROM conversations
        WHERE contact_email = %s
    """, (contact_email,))
    thread_order = cur.fetchone()[0]
    
    # 检查是否已存在（基于 contact_email + message_at + direction）
    cur.execute("""
        SELECT id FROM conversations
        WHERE contact_email = %s AND message_at = %s AND direction = %s
    """, (contact_email, ts, direction))
    if cur.fetchone():
        cur.close()
        return None
    
    cur.execute("""
        INSERT INTO conversations 
        (contact_email, direction, subject, body_text, body_html, message_at, postmark_message_id, thread_order)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (contact_email, direction, subject, body_text, body_html, ts, postmark_message_id, thread_order))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def get_conversation_thread(conn, contact_email: str) -> List[Dict]:
    """Get all messages in a conversation thread for a contact."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, direction, subject, body_text, message_at, thread_order
        FROM conversations
        WHERE contact_email = %s
        ORDER BY thread_order ASC
    """, (contact_email,))
    cols = [desc[0] for desc in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    return rows


def sync_emails_to_conversations(conn) -> int:
    """Sync existing emails table to conversations table (outbound)."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO conversations (contact_email, direction, subject, body_text, body_html, message_at, postmark_message_id, thread_order)
        SELECT 
            e.contact_email,
            'outbound',
            e.subject,
            e.body_text,
            e.body_html,
            e.sent_at,
            e.postmark_message_id,
            ROW_NUMBER() OVER (PARTITION BY e.contact_email ORDER BY e.sent_at)
        FROM emails e
        WHERE NOT EXISTS (
            SELECT 1 FROM conversations c 
            WHERE c.contact_email = e.contact_email 
            AND c.postmark_message_id = e.postmark_message_id
        )
    """)
    count = cur.rowcount
    cur.close()
    return count


def sync_replies_to_conversations(conn) -> int:
    """Sync existing replies table to conversations table (inbound)."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO conversations (contact_email, direction, subject, body_text, message_at, thread_order)
        SELECT 
            e.contact_email,
            'inbound',
            'Re: ' || e.subject,
            r.full_content,
            r.replied_at,
            (SELECT COALESCE(MAX(thread_order), 0) + 1 FROM conversations WHERE contact_email = e.contact_email)
        FROM replies r
        JOIN emails e ON e.id = r.email_id
        WHERE NOT EXISTS (
            SELECT 1 FROM conversations c 
            WHERE c.contact_email = e.contact_email 
            AND c.direction = 'inbound'
            AND c.message_at = r.replied_at
        )
    """)
    count = cur.rowcount
    cur.close()
    return count


# ── Query operations ────────────────────────────────────────────────

def get_all_contacts(conn) -> List[Dict]:
    """Return all contacts with their latest email status from the contact_status view."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM contact_status ORDER BY sent_at DESC NULLS LAST")
    cols = [desc[0] for desc in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    return rows


def get_contacts_for_sync(conn) -> List[Dict]:
    """Return contacts that need Postmark sync (not bounced, have a postmark_message_id).

    Ordered by email_id for stable, resumable iteration.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT email, postmark_message_id, email_id, status
        FROM contact_status
        WHERE postmark_message_id IS NOT NULL
          AND status != 'failed'
        ORDER BY email_id
    """)
    cols = [desc[0] for desc in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    return rows


def get_unreplied_contacts(conn) -> List[Dict]:
    """Return contacts that have been sent an email but have no reply recorded."""
    cur = conn.cursor()
    cur.execute("""
        SELECT email, chair_name, postmark_message_id, email_id, subject, sent_at
        FROM contact_status
        WHERE status NOT IN ('failed')
          AND replied_at IS NULL
          AND postmark_message_id IS NOT NULL
    """)
    cols = [desc[0] for desc in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    return rows


def get_unclassified_replies(conn) -> List[Dict]:
    """Return replies that have content but need AI classification review.

    In the DB, replies are inserted with a preliminary is_interested value
    but no classification_confidence. We use that as the indicator.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT cs.email, cs.chair_name, cs.email_id, cs.reply_snippet,
               r.id AS reply_id, r.is_interested, r.full_content
        FROM contact_status cs
        JOIN replies r ON r.email_id = cs.email_id
        WHERE r.classification_confidence IS NULL
          AND r.full_content IS NOT NULL
          AND r.full_content != ''
    """)
    cols = [desc[0] for desc in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    return rows


def get_followup_candidates(conn, min_days: int = 0) -> List[Dict]:
    """Return contacts eligible for a follow-up email.

    Eligible = delivered, no reply, no bounce, and only one email sent so far
    (i.e. no follow-up already sent).
    Optional min_days filters to contacts whose first email was sent at least
    N days ago.
    """
    cur = conn.cursor()
    day_filter = ""
    params: list = []
    if min_days > 0:
        day_filter = "AND cs.sent_at < NOW() - INTERVAL '%s days'"
        params.append(min_days)
    cur.execute(f"""
        SELECT cs.email, cs.chair_name, cs.conference,
               cs.sent_at, cs.status,
               cs.postmark_message_id, cs.subject
        FROM contact_status cs
        WHERE cs.status IN ('no_reply', 'opened_no_reply', 'clicked_no_reply')
          AND cs.bounced_at IS NULL
          AND cs.replied_at IS NULL
          {day_filter}
          AND (SELECT COUNT(*) FROM emails WHERE contact_email = cs.email) = 1
        ORDER BY cs.sent_at ASC
    """, params)
    cols = [desc[0] for desc in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    return rows


def get_status_summary(conn) -> List[Tuple[str, int]]:
    cur = conn.cursor()
    cur.execute("SELECT status, count FROM status_summary ORDER BY count DESC")
    rows = cur.fetchall()
    cur.close()
    return rows


# ── Export ───────────────────────────────────────────────────────────

def export_crm_json(conn, path: str = "crm.json"):
    """Export current DB state to crm.json format for backward compatibility."""
    contacts = get_all_contacts(conn)
    out = []
    for c in contacts:
        out.append({
            "email": c["email"],
            "chair_name": c.get("chair_name", ""),
            "conference": c.get("conference", ""),
            "subject": c.get("subject", ""),
            "status": c.get("status", "no_reply"),
            "postmark_message_id": c.get("postmark_message_id", ""),
            "sent_at": str(c["sent_at"]) if c.get("sent_at") else None,
            "delivered_at": str(c["delivered_at"]) if c.get("delivered_at") else None,
            "opened_at": str(c["opened_at"]) if c.get("opened_at") else None,
            "open_count": c.get("open_count", 0),
            "clicked_at": str(c["clicked_at"]) if c.get("clicked_at") else None,
            "bounced_at": str(c["bounced_at"]) if c.get("bounced_at") else None,
            "bounce_type": c.get("bounce_type"),
            "replied_at": str(c["replied_at"]) if c.get("replied_at") else None,
            "reply_classification": "interested" if c.get("is_interested") is True
                                    else ("rejected" if c.get("is_interested") is False
                                          else None),
            "reply_snippet": c.get("reply_snippet"),
            "last_checked": str(c["last_updated"]) if c.get("last_updated") else None,
        })
    with open(path, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=str)
    return len(out)
