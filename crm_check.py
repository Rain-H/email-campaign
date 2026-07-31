#!/usr/bin/env python3
"""
Email CRM Status Checker (Database-backed)

Tracks sent cold emails through: sent -> delivered/bounced -> clicked -> replied -> AI classified

All state is stored in PostgreSQL. Optional --export-json to dump to crm.json.

Usage:
    python3 crm_check.py                  # Full sync (Postmark + replies + classify)
    python3 crm_check.py --postmark-only  # Only check Postmark delivery/open/click
    python3 crm_check.py --replies-only   # Only check IMAP for replies
    python3 crm_check.py --report         # Show report without syncing
    python3 crm_check.py --export-json    # Export DB to crm.json after sync
"""

import argparse
import imaplib
import email as email_lib
from email.header import decode_header
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()

# ---------- config ----------

# Reply-vs-sent-time comparisons are always done in US Eastern, regardless of
# the host machine's system timezone/clock (which can't be trusted — see
# check_replies()). Do not use datetime.astimezone() with no args for this.
US_EASTERN = ZoneInfo("America/New_York")

POSTMARK_SERVER_TOKEN = os.getenv("POSTMARK_SERVER_TOKEN")
POSTMARK_API = "https://api.postmarkapp.com"
# The Postmark server is shared with other PaperFox product emails (e.g.
# notifications@paperfox.ai) — cold campaign emails always come from this
# address. Used to filter /messages/outbound server-side so bulk sync doesn't
# pull in unrelated traffic (see sync_postmark_bulk()).
POSTMARK_SENDER_EMAIL = os.getenv("POSTMARK_SENDER_EMAIL", "rain@paperfox.ai")

IMAP_SERVER = os.getenv("IMAP_SERVER", "mail.privateemail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS") or os.getenv("POSTMARK_SENDER_EMAIL")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_CLASSIFICATION_MODEL = os.getenv(
    "ANTHROPIC_CLASSIFICATION_MODEL",
    "claude-sonnet-4-6",
)


# ====================================================================
# Postmark status sync (delivery, bounces, opens, clicks)
# ====================================================================

def postmark_headers() -> Dict:
    return {
        "Accept": "application/json",
        "X-Postmark-Server-Token": POSTMARK_SERVER_TOKEN,
    }


def sync_postmark_for_contact(conn, contact: Dict) -> bool:
    """Check Postmark APIs for one contact and write updates to DB. Returns True if updated."""
    from database.crm_db import update_delivery, update_bounce, update_open, update_click

    msg_id = contact.get("postmark_message_id")
    email_addr = contact.get("email")
    if not msg_id:
        return False

    changed = False

    # 1. Message details (delivery, bounce, open, click events)
    try:
        resp = requests.get(
            f"{POSTMARK_API}/messages/outbound/{msg_id}/details",
            headers=postmark_headers(), timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            open_count = 0
            for evt in data.get("MessageEvents", []):
                evt_type = evt.get("Type", "")
                evt_time = evt.get("ReceivedAt", "")

                if evt_type == "Delivered":
                    update_delivery(conn, msg_id, evt_time)
                    changed = True
                elif evt_type == "Bounced":
                    bounce_type = evt.get("Details", {}).get("BounceType", "unknown")
                    update_bounce(conn, msg_id, evt_time, bounce_type)
                    changed = True
                elif evt_type == "Opened":
                    open_count += 1
                elif evt_type == "LinkClicked":
                    update_click(conn, msg_id, evt_time)
                    changed = True

            if open_count > 0:
                first_open = next(
                    (e["ReceivedAt"] for e in data.get("MessageEvents", []) if e.get("Type") == "Opened"),
                    ""
                )
                update_open(conn, msg_id, first_open, open_count)
                changed = True
    except Exception as e:
        print(f"    Warning: Postmark details API error for {email_addr}: {e}")

    # 2. Opens by recipient (catches opens across all messages)
    try:
        resp = requests.get(
            f"{POSTMARK_API}/messages/outbound/opens",
            headers=postmark_headers(),
            params={"recipient": email_addr, "count": 50, "offset": 0},
            timeout=15,
        )
        if resp.status_code == 200:
            opens = resp.json().get("Opens", [])
            if opens:
                first_open_time = opens[-1].get("ReceivedAt", "")
                update_open(conn, msg_id, first_open_time, len(opens))
                changed = True
    except Exception as e:
        print(f"    Warning: Postmark opens API error for {email_addr}: {e}")

    # 3. Clicks by recipient
    try:
        resp = requests.get(
            f"{POSTMARK_API}/messages/outbound/clicks",
            headers=postmark_headers(),
            params={"recipient": email_addr, "count": 50, "offset": 0},
            timeout=15,
        )
        if resp.status_code == 200:
            clicks = resp.json().get("Clicks", [])
            if clicks:
                first_click_time = clicks[-1].get("ReceivedAt", "")
                update_click(conn, msg_id, first_click_time)
                changed = True
    except Exception as e:
        print(f"    Warning: Postmark clicks API error for {email_addr}: {e}")

    return changed


def sync_postmark_per_contact(conn, start_from: int = 0, commit_every: int = 50) -> int:
    """Per-contact Postmark sync (3 API calls per contact). Slow but kept as fallback.

    Use this when bulk sync isn't suitable (e.g., debugging a single contact's status,
    or when you only need to sync a subset starting from a known index).

    Args:
        start_from: 0-based index to start from (skip the first N contacts).
                    Useful for resuming after an interrupted run.
        commit_every: Commit to DB every N contacts so partial progress is persisted.
    """
    from database.crm_db import get_contacts_for_sync

    if not POSTMARK_SERVER_TOKEN:
        print("  POSTMARK_SERVER_TOKEN not set, skipping.")
        return 0

    contacts = get_contacts_for_sync(conn)
    total = len(contacts)

    if start_from < 0:
        start_from = 0
    if start_from >= total:
        print(f"  start_from={start_from} >= total {total}, nothing to do.")
        return 0
    if start_from > 0:
        print(f"  Resuming from index {start_from} (skipping first {start_from} of {total}).")

    updated = 0
    for i in range(start_from, total):
        contact = contacts[i]
        if sync_postmark_for_contact(conn, contact):
            updated += 1
        if i < total - 1:
            time.sleep(0.3)
        if (i + 1) % 10 == 0 or i == total - 1:
            print(f"    Checked {i+1}/{total} contacts...")
        if (i + 1) % commit_every == 0:
            conn.commit()

    conn.commit()
    print(f"  {updated} contact(s) updated from Postmark.")
    return updated


def _paginate_postmark(endpoint: str, params: Optional[Dict] = None,
                       page_size: int = 500, results_key: str = "Messages") -> List[Dict]:
    """Generator-style helper to paginate a Postmark bulk endpoint.

    Yields each page's items list. Stops when:
      - empty page is returned
      - we've collected TotalCount items
      - an HTTP error occurs
    """
    params = dict(params or {})
    params["count"] = page_size
    offset = 0
    while True:
        params["offset"] = offset
        try:
            resp = requests.get(
                f"{POSTMARK_API}{endpoint}",
                headers=postmark_headers(),
                params=params,
                timeout=30,
            )
        except Exception as e:
            print(f"    Warning: {endpoint} page offset={offset}: {e}")
            return
        if resp.status_code != 200:
            print(f"    Warning: {endpoint} HTTP {resp.status_code}: {resp.text[:200]}")
            return
        data = resp.json()
        items = data.get(results_key, [])
        total = data.get("TotalCount", 0)
        if not items:
            return
        yield items, offset + len(items), total
        offset += len(items)
        if offset >= total or len(items) < page_size:
            return


def _date_chunks(from_date: str, to_date: Optional[str] = None, chunk_days: int = 30):
    """Yield (chunk_from, chunk_to) date strings (YYYY-MM-DD) covering
    [from_date, to_date] in chunk_days-sized inclusive windows. to_date
    defaults to today (UTC)."""
    start = datetime.strptime(from_date, "%Y-%m-%d").date()
    end = (datetime.strptime(to_date, "%Y-%m-%d").date() if to_date
           else datetime.now(timezone.utc).date())
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=chunk_days - 1), end)
        yield cur.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")
        cur = chunk_end + timedelta(days=1)


def _paginate_postmark_windowed(endpoint: str, params: Optional[Dict], from_date: Optional[str],
                                page_size: int = 500, results_key: str = "Messages",
                                chunk_days: int = 30):
    """Like _paginate_postmark, but splits [from_date, today] into chunk_days
    windows and queries each window separately.

    Needed for endpoints that can't be filtered by sender email (/bounces,
    /opens, /clicks): on a shared Postmark account with heavy unrelated
    traffic, one query spanning a whole multi-month campaign can return more
    items than Postmark's ~10000 offset+count pagination ceiling and fail
    with a 422 partway through. Chunking keeps each individual query's
    TotalCount well under that ceiling no matter how long the campaign has
    been running — narrowing just the start date (an earlier version of this
    code tried that) does NOT fix this, since the ceiling is about how much
    activity falls *inside* the window, not how far back the window starts.
    """
    if not from_date:
        yield from _paginate_postmark(endpoint, params, page_size, results_key)
        return
    for chunk_from, chunk_to in _date_chunks(from_date, chunk_days=chunk_days):
        chunk_params = dict(params or {}, fromdate=chunk_from, todate=chunk_to)
        pages = 0
        for items, fetched, total in _paginate_postmark(endpoint, chunk_params, page_size, results_key):
            pages += 1
            print(f"      [{chunk_from}..{chunk_to}] page {pages}: scanned {fetched}/{total}")
            yield items, fetched, total


def sync_postmark_bulk(conn, from_date: Optional[str] = None,
                       page_size: int = 500) -> int:
    """Bulk Postmark sync using batch endpoints. Returns count of updated contacts.

    Replaces per-contact sync (3 API calls × N contacts = thousands of calls) with
    a handful of paginated bulk calls. Typically completes in 1-2 minutes for ~3000
    contacts vs hours for per-contact mode.

    Args:
        from_date: Optional 'YYYY-MM-DD' to limit bulk queries to messages on/after
                   this date. Defaults to the day before our earliest tracked send
                   (see below) if not given.
        page_size: Page size for each bulk endpoint (Postmark max is 500).
    """
    from database.crm_db import (
        get_contacts_for_sync, update_delivery, update_bounce,
        update_open, update_click,
    )

    if not POSTMARK_SERVER_TOKEN:
        print("  POSTMARK_SERVER_TOKEN not set, skipping.")
        return 0

    contacts = get_contacts_for_sync(conn)
    our_msg_ids = {c["postmark_message_id"] for c in contacts if c.get("postmark_message_id")}
    if not our_msg_ids:
        print("  No tracked messages found, nothing to sync.")
        return 0

    if not from_date:
        # Default to the day before our earliest tracked send, so the sync
        # covers the whole campaign without guessing an arbitrary lookback
        # window. This is about not missing our own old messages — it does
        # NOT protect against the pagination ceiling below (see
        # _paginate_postmark_windowed's docstring for why not).
        sent_dates = [c["sent_at"] for c in contacts if c.get("sent_at")]
        if sent_dates:
            from_date = (min(sent_dates) - timedelta(days=1)).strftime("%Y-%m-%d")
    if from_date:
        print(f"  Bulk sync for {len(our_msg_ids)} tracked messages (fromdate={from_date})...")
    else:
        print(f"  Bulk sync for {len(our_msg_ids)} tracked messages...")

    updated_ids: set = set()

    # 1. Bounces first (gives BouncedAt + Type). Must run before step 2 —
    # /messages/outbound's Status field only means "accepted by Postmark for
    # sending", not a delivery confirmation from the recipient's mail server
    # (that requires the per-message /details endpoint's "Delivered" event,
    # which sync_postmark_for_contact() uses). Fetching bounces first lets us
    # skip marking a bounced message as delivered_at below, instead of
    # setting both and letting the contact_status view's bounce-wins CASE
    # mask the contradiction while the funnel report double-counts it.
    print("    [1/4] /bounces (bounce details)...")
    bounced_ids: set = set()
    for items, fetched, total in _paginate_postmark_windowed(
        "/bounces", {}, from_date, page_size, results_key="Bounces"
    ):
        for b in items:
            msg_id = b.get("MessageID")
            if msg_id not in our_msg_ids:
                continue
            bounced_at = b.get("BouncedAt", "")
            bounce_type = b.get("Type", "unknown")
            update_bounce(conn, msg_id, bounced_at, bounce_type)
            bounced_ids.add(msg_id)
            updated_ids.add(msg_id)
    conn.commit()

    # 2. Message status (Sent/Processed -> delivered), skipping anything we
    # now know bounced. Filtered server-side by fromemail — this account's
    # /messages/outbound also contains unrelated PaperFox product email
    # traffic (see POSTMARK_SENDER_EMAIL comment above), and without this
    # filter the endpoint can return far more rows than our tracked messages.
    # Only this endpoint supports fromemail; /bounces, /opens, /clicks don't,
    # so those use _paginate_postmark_windowed (date-chunked) instead to
    # avoid Postmark's offset+count pagination ceiling (~10000, 422).
    print("    [2/4] /messages/outbound (status & delivery)...")
    outbound_params: Dict = {"fromemail": POSTMARK_SENDER_EMAIL}
    if from_date:
        outbound_params["fromdate"] = from_date
    pages = 0
    for items, fetched, total in _paginate_postmark(
        "/messages/outbound", outbound_params, page_size, results_key="Messages"
    ):
        pages += 1
        for m in items:
            msg_id = m.get("MessageID")
            if msg_id not in our_msg_ids or msg_id in bounced_ids:
                continue
            status = m.get("Status", "")
            received_at = m.get("ReceivedAt", "")
            if status in ("Sent", "Processed"):
                update_delivery(conn, msg_id, received_at)
                updated_ids.add(msg_id)
        print(f"      page {pages}: scanned {fetched}/{total}")
    conn.commit()

    # 3. Opens (aggregate count + earliest timestamp per message).
    # NOT windowed: confirmed by direct testing (2026-07-31) that this
    # endpoint silently ignores fromdate/todate entirely — TotalCount is
    # identical whether queried with no filter or a narrow one-week window.
    # So date-chunking here would just re-scan the same full account on
    # every chunk for no benefit. There is no known server-side way to
    # narrow this query to our own messages or a date range; the only real
    # fix would be reverting to per-contact calls with `recipient=`, which
    # reintroduces the N-calls-per-contact problem this bulk path exists to
    # avoid. Practical result: only the first ~10000 opens account-wide are
    # visible before hitting Postmark's pagination ceiling (422, caught
    # below); anything beyond that is silently missed. Acceptable in
    # practice since the funnel report already flags open counts as
    # "approx, pixel-based, unreliable".
    print("    [3/4] /messages/outbound/opens...")
    opens_by_msg: Dict[str, List[str]] = {}
    pages = 0
    for items, fetched, total in _paginate_postmark(
        "/messages/outbound/opens", {}, page_size, results_key="Opens"
    ):
        pages += 1
        for o in items:
            msg_id = o.get("MessageID")
            if msg_id not in our_msg_ids:
                continue
            ts = o.get("ReceivedAt", "")
            if ts:
                opens_by_msg.setdefault(msg_id, []).append(ts)
        print(f"      page {pages}: scanned {fetched}/{total}")
    for msg_id, ts_list in opens_by_msg.items():
        # Earliest timestamp = first open (ISO 8601 sorts lexicographically)
        first_open = min(ts_list)
        update_open(conn, msg_id, first_open, len(ts_list))
        updated_ids.add(msg_id)
    conn.commit()

    # 4. Clicks (earliest timestamp per message). Same caveat as opens above
    # — /messages/outbound/clicks also ignores fromdate/todate (confirmed).
    print("    [4/4] /messages/outbound/clicks...")
    clicks_by_msg: Dict[str, str] = {}
    pages = 0
    for items, fetched, total in _paginate_postmark(
        "/messages/outbound/clicks", {}, page_size, results_key="Clicks"
    ):
        pages += 1
        for c in items:
            msg_id = c.get("MessageID")
            if msg_id not in our_msg_ids:
                continue
            ts = c.get("ReceivedAt", "")
            if not ts:
                continue
            if msg_id not in clicks_by_msg or ts < clicks_by_msg[msg_id]:
                clicks_by_msg[msg_id] = ts
        print(f"      page {pages}: scanned {fetched}/{total}")
    for msg_id, ts in clicks_by_msg.items():
        update_click(conn, msg_id, ts)
        updated_ids.add(msg_id)
    conn.commit()

    print(f"  {len(updated_ids)} contact(s) updated from Postmark.")
    return len(updated_ids)


def sync_postmark(conn, *, bulk: bool = True, from_date: Optional[str] = None,
                  start_from: int = 0, commit_every: int = 50) -> int:
    """Postmark sync dispatcher. Defaults to fast bulk mode; falls back to per-contact.

    Args:
        bulk: When True (default), use the bulk-API path. When False, use the
              per-contact path (slow but supports --start-from resume).
        from_date: 'YYYY-MM-DD' filter for bulk mode.
        start_from: 0-based start index for per-contact mode.
        commit_every: Commit cadence for per-contact mode.
    """
    if bulk:
        return sync_postmark_bulk(conn, from_date=from_date)
    return sync_postmark_per_contact(conn, start_from=start_from, commit_every=commit_every)


# ====================================================================
# IMAP reply detection
# ====================================================================

def decode_mime_header(header: str) -> str:
    if not header:
        return ""
    decoded_parts = decode_header(header)
    result = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(encoding or "utf-8", errors="ignore"))
        else:
            result.append(part)
    return "".join(result)


def _html_to_text(html: str) -> str:
    """Very small HTML->text fallback for replies with no text/plain part."""
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    except Exception:
        # bs4 not available or parse failure: crude tag strip so we at least
        # get *something* instead of leaving full_content empty.
        return re.sub(r"<[^>]+>", " ", html)


def get_email_body(msg) -> str:
    """Extract reply body text, preferring text/plain but falling back to
    text/html (converted to plain text) when no plain-text part exists.

    Without the HTML fallback, HTML-only replies come back as an empty
    string; downstream, get_unclassified_replies() filters out empty
    full_content, so those replies would never reach AI classification and
    would sit permanently as the default is_interested=False — silently
    losing genuinely interested replies that happened to be sent in HTML.
    """
    plain_body = ""
    html_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain" and not plain_body:
                try:
                    plain_body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                except Exception:
                    pass
            elif ctype == "text/html" and not html_body:
                try:
                    html_body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        except Exception:
            payload = ""
        if msg.get_content_type() == "text/html":
            html_body = payload
        else:
            plain_body = payload

    body = plain_body.strip() or (_html_to_text(html_body).strip() if html_body else "")
    return body[:1000]


def extract_email_address(header: str) -> str:
    if "<" in header and ">" in header:
        return header.split("<")[1].split(">")[0].strip().lower()
    return header.strip().lower()


def parse_email_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


_SUBJECT_PREFIX_RE = re.compile(r"^\s*(?:(?:re|fwd?|aw|sv|antw)\s*:\s*|\[ext\]\s*)+", re.IGNORECASE)


def _normalize_subject(subject: str) -> str:
    """Strip leading Re:/Fwd:/Aw:/[EXT] chains so subjects can be compared
    regardless of how many reply/forward prefixes a mail client stacked on."""
    return _SUBJECT_PREFIX_RE.sub("", subject or "").strip().lower()


def is_reply_to_campaign(msg, contact: Dict) -> bool:
    """Check if an email is a genuine reply to a campaign message.

    Two independent signals, either is sufficient:
      1. Threading headers (In-Reply-To / References) contain our Postmark
         Message-ID — the strongest signal, present whenever the recipient's
         mail client replied normally.
      2. Subject matches the original campaign subject once Re:/Fwd:/Aw:/
         [EXT] prefixes are stripped from both sides — looser than an exact
         "Re: <subject>" match so it still works after multiple hops
         (e.g. "Fwd: Re: [EXT] Re: Quick question...").
    """
    msg_id = contact.get("postmark_message_id", "")

    if msg_id:
        in_reply_to = msg.get("In-Reply-To", "")
        references = msg.get("References", "")
        if msg_id in in_reply_to or msg_id in references:
            return True

    subject = decode_mime_header(msg.get("Subject", ""))
    campaign_subject = contact.get("subject", "")
    if campaign_subject and _normalize_subject(subject) == _normalize_subject(campaign_subject):
        return True

    return False


def is_auto_reply(subject: str) -> bool:
    """Check if an email is an auto-reply based on subject."""
    auto_keywords = [
        "automatisch", "automatic", "auto-reply", "autoreply",
        "réponse automatique", "out of office", "away from",
        "antwoord", "antwort", "abwesend"
    ]
    subject_lower = subject.lower()
    return any(kw in subject_lower for kw in auto_keywords)


def check_replies(conn, since_days: int = 30) -> int:
    """Check IMAP inbox for replies using FROM-based search.

    Searches for emails from contacts in the database (FROM + SINCE), then
    disambiguates among matches using is_reply_to_campaign() (threading
    headers, falling back to a loosened subject match). FROM-based search
    alone is used as the *candidate* filter because subject-based search is
    unreliable across Re:/Fwd:/[EXT] prefix variations, but without the
    is_reply_to_campaign() check, ANY email from that address after the send
    date — even one unrelated to this campaign — would get recorded as a
    "reply", silently blocking future follow-ups and skewing reply-rate
    stats. When a contact has multiple matching messages, a verified one is
    always preferred over an unverified one.
    """
    from database.crm_db import get_unreplied_contacts, insert_reply

    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print("  EMAIL_ADDRESS / EMAIL_PASSWORD not set, skipping IMAP.")
        return 0

    contacts = get_unreplied_contacts(conn)
    if not contacts:
        print("  No contacts to check replies for.")
        return 0

    contact_map = {c["email"].lower(): c for c in contacts}
    print(f"  Checking replies from {len(contacts)} unreplied contacts...")

    found = 0
    checked = 0
    seen_contacts = set()

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("INBOX")
        print(f"  Connected to {IMAP_SERVER}")

        since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")

        for contact in contacts:
            contact_email = contact["email"].lower()
            
            if contact_email in seen_contacts:
                continue
            seen_contacts.add(contact_email)

            checked += 1
            if checked % 100 == 0:
                print(f"    Checked {checked}/{len(contacts)} contacts...")

            search_criteria = f'(SINCE "{since_date}" FROM "{contact_email}")'
            try:
                status, messages = mail.search(None, search_criteria)
                if status != "OK":
                    continue

                email_ids = messages[0].split()
                if not email_ids:
                    continue

                # Collect all plausible candidates first instead of acting on
                # the first FROM/SINCE match — that match could easily be an
                # unrelated email from this address. We pick the best one below.
                candidates = []
                for eid in email_ids:
                    st, msg_data = mail.fetch(eid, "(RFC822)")
                    if st != "OK":
                        continue

                    raw = msg_data[0][1]
                    msg = email_lib.message_from_bytes(raw)

                    from_header = decode_mime_header(msg.get("From", ""))
                    from_email = extract_email_address(from_header)
                    subject = decode_mime_header(msg.get("Subject", ""))

                    if from_email == EMAIL_ADDRESS.lower():
                        continue

                    if is_auto_reply(subject):
                        print(f"    Skipping auto-reply from {from_email}")
                        continue

                    reply_date = parse_email_date(msg.get("Date", ""))
                    sent_at_str = str(contact.get("sent_at", ""))
                    if reply_date and sent_at_str:
                        try:
                            # sent_at is stored naive but always in UTC (see
                            # _parse_timestamp() in database/crm_db.py) — tag
                            # it explicitly rather than letting astimezone()
                            # guess based on the host's system timezone/clock.
                            sent_dt = datetime.fromisoformat(sent_at_str.replace("Z", "+00:00"))
                            if sent_dt.tzinfo is None:
                                sent_dt = sent_dt.replace(tzinfo=timezone.utc)
                            sent_dt = sent_dt.astimezone(US_EASTERN)
                            reply_date_tz = reply_date.astimezone(US_EASTERN)
                            if reply_date_tz < sent_dt:
                                continue
                        except Exception:
                            pass

                    candidates.append({
                        "from_email": from_email,
                        "subject": subject,
                        "date_str": msg.get("Date", ""),
                        "body": get_email_body(msg),
                        "verified": is_reply_to_campaign(msg, contact),
                    })

                if not candidates:
                    continue

                # Prefer a verified match (threading headers or normalized
                # subject match) over an unverified one; among ties, keep IMAP
                # search order (oldest first).
                chosen = next((c for c in candidates if c["verified"]), candidates[0])
                if not chosen["verified"] and len(candidates) > 0:
                    print(f"    ! No campaign-thread match for {contact_email}; "
                          f"using earliest FROM-matched email as best guess "
                          f"(subject: {chosen['subject'][:50]!r})")

                reply_id = insert_reply(
                    conn, contact["email_id"], chosen["date_str"], chosen["body"], False
                )
                if reply_id:
                    found += 1
                    verified_tag = "" if chosen["verified"] else " [unverified]"
                    print(f"    Reply from {chosen['from_email']} "
                          f"(subject: {chosen['subject'][:50]}){verified_tag}")

            except Exception as e:
                print(f"    ! Error checking replies for {contact_email}: {e}")

        conn.commit()
        mail.logout()
    except Exception as e:
        print(f"  IMAP error: {e}")

    print(f"  Found {found} new reply(ies).")
    return found


# ====================================================================
# Sync sent emails from IMAP Sent folder
# ====================================================================

def sync_sent_emails(conn, since_days: int = 60) -> int:
    """Sync sent emails from IMAP Sent folder to conversations table.
    
    This captures manual replies we sent to contacts (not through send_postmark.py).
    """
    from database.crm_db import insert_conversation
    
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print("  EMAIL_ADDRESS / EMAIL_PASSWORD not set, skipping.")
        return 0

    # Get all contact emails from database (preserve original case)
    cur = conn.cursor()
    cur.execute("SELECT email FROM contacts")
    contact_emails_original = {row[0] for row in cur.fetchall()}
    # Create lowercase mapping for IMAP search
    email_case_map = {e.lower(): e for e in contact_emails_original}
    cur.close()
    
    if not contact_emails_original:
        print("  No contacts in database.")
        return 0

    print(f"  Checking Sent folder for emails to {len(contact_emails_original)} contacts...")
    
    found = 0
    
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        
        # Try different Sent folder names
        sent_folders = ["Sent", "INBOX.Sent", "Sent Items", "INBOX.Sent Items"]
        selected = False
        for folder in sent_folders:
            try:
                status, _ = mail.select(folder)
                if status == "OK":
                    print(f"  Connected to {folder}")
                    selected = True
                    break
            except Exception:
                continue
        
        if not selected:
            print("  Could not find Sent folder.")
            mail.logout()
            return 0

        since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
        
        for contact_email_lower in email_case_map.keys():
            original_email = email_case_map[contact_email_lower]
            search_criteria = f'(SINCE "{since_date}" TO "{contact_email_lower}")'
            try:
                status, messages = mail.search(None, search_criteria)
                if status != "OK":
                    continue

                email_ids = messages[0].split()
                if not email_ids:
                    continue

                for eid in email_ids:
                    status, data = mail.fetch(eid, "(RFC822)")
                    if status != "OK":
                        continue

                    msg = email_lib.message_from_bytes(data[0][1])
                    
                    # Get subject
                    subject = decode_mime_header(msg.get("Subject", ""))
                    
                    # Get date
                    date_str = msg.get("Date", "")
                    sent_at = None
                    if date_str:
                        try:
                            from email.utils import parsedate_to_datetime
                            sent_at = parsedate_to_datetime(date_str).strftime("%Y-%m-%d %H:%M:%S")
                        except Exception:
                            pass
                    
                    if not sent_at:
                        continue
                    
                    # Get body
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                payload = part.get_payload(decode=True)
                                if payload:
                                    charset = part.get_content_charset() or "utf-8"
                                    body = payload.decode(charset, errors="replace")
                                    break
                    else:
                        payload = msg.get_payload(decode=True)
                        if payload:
                            charset = msg.get_content_charset() or "utf-8"
                            body = payload.decode(charset, errors="replace")
                    
                    # Insert into conversations (use original case email)
                    result = insert_conversation(
                        conn,
                        contact_email=original_email,
                        direction="outbound",
                        subject=subject,
                        body_text=body,
                        message_at=sent_at
                    )
                    if result:
                        found += 1
                        print(f"    Synced sent email to {original_email}: {subject[:40]}")

            except Exception as e:
                print(f"    ! Error syncing sent emails to {original_email}: {e}")
                continue

        conn.commit()
        mail.logout()
    except Exception as e:
        print(f"  IMAP error: {e}")

    print(f"  Synced {found} sent email(s) to conversations.")
    return found


# ====================================================================
# AI classification of replies
# ====================================================================

CLASSIFY_PROMPT = """Analyze this email reply to a cold outreach about PaperFox.ai (a conference management platform).

EMAIL CONTENT:
---
{body}
---

Classify into ONE category:
- interested: Wants a demo, asks about features, positive tone, accepts meeting
- rejected: Declines, unsubscribe, not interested, already has solution

Respond in JSON:
{{"classification": "interested|rejected", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}"""


def classify_replies(conn) -> int:
    """Classify unclassified replies using Claude. Writes directly to DB."""
    from database.crm_db import get_unclassified_replies, update_reply_classification

    if not ANTHROPIC_API_KEY:
        print("  ANTHROPIC_API_KEY not set, skipping classification.")
        return 0

    unclassified = get_unclassified_replies(conn)
    if not unclassified:
        print("  No unclassified replies.")
        return 0

    print(f"  Classifying {len(unclassified)} reply(ies) with Claude...")

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    except ImportError:
        print("  anthropic package not installed. Run: pip install anthropic")
        return 0

    classified = 0
    for reply in unclassified:
        try:
            body = reply.get("full_content") or reply.get("reply_snippet", "")
            prompt = CLASSIFY_PROMPT.format(body=body)
            response = client.messages.create(
                model=ANTHROPIC_CLASSIFICATION_MODEL,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            match = re.search(r"\{[\s\S]*?\}", text)
            if match:
                result = json.loads(match.group())
                classification = result.get("classification", "rejected")
                is_interested = classification == "interested"
                confidence = result.get("confidence")
                reasoning = result.get("reasoning")
                update_reply_classification(
                    conn, reply["email_id"], is_interested, confidence, reasoning
                )
                classified += 1
                label = "interested" if is_interested else "rejected"
                print(f"    {reply['email']}: {label}")
        except Exception as e:
            print(f"    Error classifying {reply['email']}: {e}")

        time.sleep(0.5)

    conn.commit()
    print(f"  Classified {classified} reply(ies).")
    return classified


# ====================================================================
# Report (reads from DB)
# ====================================================================

# DB status values for display ordering
DB_STATUS_ORDER = [
    "no_reply",
    "opened_no_reply",
    "clicked_no_reply",
    "replied_interested",
    "replied_not_interested",
    "failed",
]


def print_report(conn):
    """Print a formatted CRM status report from the database."""
    from database.crm_db import get_all_contacts, get_status_summary

    contacts = get_all_contacts(conn)

    print()
    print("=" * 72)
    print("  EMAIL CRM STATUS REPORT")
    print("=" * 72)

    if not contacts:
        print("  No contacts in CRM yet.")
        print("=" * 72)
        return

    total = len(contacts)
    delivered = sum(1 for c in contacts if c.get("delivered_at"))
    bounced = sum(1 for c in contacts if c.get("bounced_at"))
    clicked = sum(1 for c in contacts if c.get("clicked_at"))
    replied = sum(1 for c in contacts if c.get("replied_at"))
    opened = sum(1 for c in contacts if c.get("opened_at"))

    print(f"\n  Total contacts: {total}")
    print()
    print("  ENGAGEMENT FUNNEL:")
    print(f"    Sent:      {total}")
    if total:
        print(f"    Delivered: {delivered}  ({delivered/total*100:.0f}%)")
        print(f"    Bounced:   {bounced}  ({bounced/total*100:.0f}%)")
        print(f"    Clicked:   {clicked}  ({clicked/total*100:.0f}%)")
        print(f"    Replied:   {replied}  ({replied/total*100:.0f}%)")
        print()
        print(f"    ~Opened:   ~{opened}  (approx, pixel-based, unreliable)")

    # Status breakdown from DB view
    summary = get_status_summary(conn)
    print()
    print("  STATUS BREAKDOWN:")
    for status, count in summary:
        bar = "#" * count
        print(f"    {status:<25} {count:>4}  {bar}")

    # Contact table
    print()
    print("  CONTACTS:")
    print(f"    {'Name':<22} {'Email':<30} {'Conference':<14} {'Status':<25}")
    print("    " + "-" * 90)
    for c in contacts:
        name = (c.get("chair_name") or "")[:20]
        em = (c.get("email") or "")[:28]
        conf = (c.get("conference") or "")[:12]
        st = c.get("status", "")
        print(f"    {name:<22} {em:<30} {conf:<14} {st}")

    print()
    print("=" * 72)


# ====================================================================
# Main
# ====================================================================

def main():
    from database.db_config import get_connection
    from database.crm_db import export_crm_json, sync_emails_to_conversations, sync_replies_to_conversations

    parser = argparse.ArgumentParser(description="Email CRM Status Checker")
    parser.add_argument("--postmark-only", action="store_true", help="Only check Postmark status")
    parser.add_argument("--replies-only", action="store_true", help="Only check for replies")
    parser.add_argument("--report", action="store_true", help="Show report without syncing")
    parser.add_argument("--since-days", type=int, default=30, help="IMAP search window (days)")
    parser.add_argument("--export-json", action="store_true", help="Export DB to crm.json after sync")
    parser.add_argument("--test", action="store_true", help="Use test database (crm_test) instead of production")
    parser.add_argument("--per-contact", action="store_true",
                        help="Use the slow per-contact Postmark sync instead of the default bulk-API mode")
    parser.add_argument("--from-date", type=str, default=None,
                        help="Bulk-mode only: limit Postmark queries to messages on/after YYYY-MM-DD "
                             "(default: the day before our earliest tracked send)")
    parser.add_argument("--start-from", type=int, default=0,
                        help="Per-contact mode only: resume from this 0-based contact index")
    parser.add_argument("--commit-every", type=int, default=50,
                        help="Per-contact mode only: commit to DB every N contacts (default: 50)")
    args = parser.parse_args()

    if args.test:
        os.environ["USE_TEST_DB"] = "1"
        print("[TEST MODE] Using test database crm_test\n")

    conn = get_connection()

    full_sync = not (args.postmark_only or args.replies_only or args.report)

    if args.report:
        print_report(conn)
        if args.export_json:
            n = export_crm_json(conn)
            print(f"Exported {n} contacts to crm.json")
        conn.close()
        return

    # Step 1: Postmark status sync
    if full_sync or args.postmark_only:
        print("\n[Step 1] Checking Postmark delivery/open/click status...")
        sync_postmark(
            conn,
            bulk=not args.per_contact,
            from_date=args.from_date,
            start_from=args.start_from,
            commit_every=args.commit_every,
        )

    # Step 2: IMAP reply detection
    if full_sync or args.replies_only:
        print("\n[Step 2] Checking IMAP for replies...")
        check_replies(conn, since_days=args.since_days)

    # Step 3: AI classification
    if full_sync or args.replies_only:
        print("\n[Step 3] Classifying replies with AI...")
        classify_replies(conn)

    # Step 4: Sync sent emails from IMAP
    if full_sync or args.replies_only:
        print("\n[Step 4] Syncing sent emails from IMAP Sent folder...")
        sync_sent_emails(conn, since_days=args.since_days)

    # Step 5: Sync to conversations table
    if full_sync or args.replies_only:
        print("\n[Step 5] Syncing to conversations table...")
        outbound_count = sync_emails_to_conversations(conn)
        inbound_count = sync_replies_to_conversations(conn)
        conn.commit()
        print(f"  Synced {outbound_count} outbound + {inbound_count} inbound messages to conversations.")

    # Report
    print_report(conn)

    if args.export_json:
        n = export_crm_json(conn)
        print(f"Exported {n} contacts to crm.json")

    conn.close()
    print("Database updated.")


if __name__ == "__main__":
    main()
