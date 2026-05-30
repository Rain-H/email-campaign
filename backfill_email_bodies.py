#!/usr/bin/env python3
"""
Backfill emails.body_text / body_html from Postmark API.

The send code historically did not store rendered bodies in the DB, even
though the schema reserves columns for them. This script fills in the gap
for previously-sent emails so that follow-ups can forward what was actually
delivered rather than re-rendering the template (which drifts when
templates / placeholders / defaults change).

Postmark retains outbound message bodies for ~45 days. Anything older will
return 404 and be reported but skipped.

Usage:
    python backfill_email_bodies.py                  # dry run (shows summary only)
    python backfill_email_bodies.py --apply          # actually write to DB
    python backfill_email_bodies.py --limit 5 --apply
    python backfill_email_bodies.py --test           # use crm_test
"""
import argparse
import os
import sys
import time
from typing import Dict, Optional, Tuple

import requests
from dotenv import load_dotenv

from database.db_config import get_connection

load_dotenv()

POSTMARK_SERVER_TOKEN = os.getenv("POSTMARK_SERVER_TOKEN")
POSTMARK_MSG_URL = "https://api.postmarkapp.com/messages/outbound/{message_id}/details"

# Postmark allows up to 10 req/sec on the messages API; be conservative.
SLEEP_BETWEEN_REQUESTS = 0.15


def make_session() -> requests.Session:
    """Postmark is public; never route through HTTP_PROXY (which may be local)."""
    s = requests.Session()
    s.trust_env = False
    s.headers.update({
        "Accept": "application/json",
        "X-Postmark-Server-Token": POSTMARK_SERVER_TOKEN,
    })
    return s


def fetch_message_body(session: requests.Session, message_id: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Return (status, text_body, html_body) for one Postmark message.

    status: 'ok' | 'not_found' (older than 45d) | 'error:<reason>'
    """
    try:
        resp = session.get(POSTMARK_MSG_URL.format(message_id=message_id), timeout=30)
    except Exception as e:
        return f"error:{type(e).__name__}", None, None

    if resp.status_code == 404:
        return "not_found", None, None
    if resp.status_code != 200:
        return f"error:http_{resp.status_code}", None, None

    try:
        data = resp.json()
    except Exception:
        return "error:non_json", None, None

    return "ok", data.get("TextBody"), data.get("HtmlBody")


def fetch_target_rows(conn, only_followup_candidates: bool) -> list:
    """Return list of (id, contact_email, postmark_message_id, subject, sent_at)."""
    cur = conn.cursor()
    base_where = """
        WHERE e.body_text IS NULL
          AND e.postmark_message_id IS NOT NULL
          AND e.postmark_message_id <> ''
    """
    if only_followup_candidates:
        cur.execute(f"""
            SELECT e.id, e.contact_email, e.postmark_message_id, e.subject, e.sent_at
            FROM emails e
            JOIN contact_status cs ON cs.email_id = e.id
            {base_where}
              AND cs.status IN ('no_reply', 'opened_no_reply', 'clicked_no_reply')
              AND cs.bounced_at IS NULL
              AND cs.replied_at IS NULL
              AND (SELECT COUNT(*) FROM emails WHERE contact_email = cs.email) = 1
            ORDER BY e.sent_at DESC
        """)
    else:
        cur.execute(f"""
            SELECT e.id, e.contact_email, e.postmark_message_id, e.subject, e.sent_at
            FROM emails e
            {base_where}
            ORDER BY e.sent_at DESC
        """)
    rows = cur.fetchall()
    cur.close()
    return rows


def update_body(conn, email_id: int, text_body: Optional[str], html_body: Optional[str]) -> None:
    cur = conn.cursor()
    cur.execute("""
        UPDATE emails
        SET body_text = COALESCE(%s, body_text),
            body_html = COALESCE(%s, body_html)
        WHERE id = %s
    """, (text_body, html_body, email_id))
    cur.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Actually write to DB (otherwise dry-run summary only)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Only process the first N rows (0 = all)")
    parser.add_argument("--all-history", action="store_true",
                        help="Backfill every NULL-body email (default: only follow-up candidates)")
    parser.add_argument("--test", action="store_true", help="Use crm_test database")
    parser.add_argument("--commit-every", type=int, default=25,
                        help="Commit to DB every N successful fetches")
    args = parser.parse_args()

    if args.test:
        os.environ["USE_TEST_DB"] = "1"
        print("[TEST MODE]\n")

    if not POSTMARK_SERVER_TOKEN:
        print("ERROR: POSTMARK_SERVER_TOKEN not set in .env")
        sys.exit(1)

    conn = get_connection()
    rows = fetch_target_rows(conn, only_followup_candidates=not args.all_history)
    if args.limit > 0:
        rows = rows[:args.limit]

    label = "all-history" if args.all_history else "follow-up candidates"
    print(f"Found {len(rows)} emails to backfill (scope: {label})")

    if not args.apply:
        print("\nDRY RUN — re-run with --apply to actually fetch+write.")
        for r in rows[:5]:
            print(f"  would fetch: id={r[0]} sent={r[4]}  mid={r[2][:8]}…  {r[1]}")
        if len(rows) > 5:
            print(f"  ... and {len(rows)-5} more")
        conn.close()
        return

    session = make_session()

    counts: Dict[str, int] = {"ok": 0, "not_found": 0, "error": 0}
    updated_ids = []

    for i, (email_id, contact_email, message_id, subject, sent_at) in enumerate(rows, 1):
        status, text_body, html_body = fetch_message_body(session, message_id)

        if status == "ok" and (text_body or html_body):
            update_body(conn, email_id, text_body, html_body)
            counts["ok"] += 1
            updated_ids.append(email_id)
        elif status == "not_found":
            counts["not_found"] += 1
        else:
            counts["error"] += 1
            print(f"  [error] id={email_id} {contact_email}: {status}")

        if i % 10 == 0 or i == len(rows):
            print(f"  {i}/{len(rows)}  ok={counts['ok']} not_found={counts['not_found']} err={counts['error']}", flush=True)

        if counts["ok"] and counts["ok"] % args.commit_every == 0 and (i % args.commit_every == 0):
            conn.commit()

        time.sleep(SLEEP_BETWEEN_REQUESTS)

    conn.commit()
    conn.close()

    print("\n=== Backfill complete ===")
    print(f"  Fetched & stored: {counts['ok']}")
    print(f"  Older than 45d (skipped): {counts['not_found']}")
    print(f"  Errors: {counts['error']}")


if __name__ == "__main__":
    main()
