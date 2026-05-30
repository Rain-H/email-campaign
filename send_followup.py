#!/usr/bin/env python3
"""Send follow-up emails as forwards of the original outreach.

Queries PostgreSQL for contacts who received the initial campaign email
but have not replied, then sends a follow-up that forwards the original
email with a new introductory note on top.
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from send_postmark import (
    render,
    plain_to_html,
    extract_greeting_name,
    POSTMARK_API_URL,
)

load_dotenv()

POSTMARK_SERVER_TOKEN = os.getenv("POSTMARK_SERVER_TOKEN")
SENDER_EMAIL = os.getenv("POSTMARK_SENDER_EMAIL", "rain@paperfox.ai")


def load_followup_body(path="followup-1.md"):
    """Load follow-up template body (no Subject line)."""
    with open(path, "r") as f:
        return f.read().strip()


def build_forwarded_body(followup_text, original_subject, original_body, sender):
    """Build the full email with forwarded original below the new note.

    `original_body` MUST be the exact body that was originally delivered
    (read from emails.body_text in the DB). Re-rendering the template at
    follow-up time is not safe — templates, [Platform] defaults, conference
    naming, etc. all drift over time, so the forwarded content would no
    longer match what the recipient actually received.
    """
    plain = (
        f"{followup_text}\n\n"
        f"---------- Forwarded message ----------\n"
        f"From: {sender}\n"
        f"Subject: {original_subject}\n\n"
        f"{original_body}"
    )
    return plain


def send_forward(recipient, subject, plain_body, html_body, dry_run=True):
    """Send a follow-up as a forward (new email, no threading headers).

    Carries the full rendered plain_body / html_body in the result so
    save_to_db() can store them on the new emails row — preserving the same
    "the DB is the source of truth for what was sent" invariant that
    send_postmark.py now follows.
    """
    result = {
        "email": recipient["email"],
        "conference": recipient["conference"],
        "chair_name": recipient["chair_name"],
        "subject": subject,
        "plain_body": plain_body,
        "html_body": html_body,
    }

    if dry_run:
        result["status"] = "dry_run"
        return result

    try:
        # Bypass HTTP(S)_PROXY env vars (same fix as send_postmark.py): Postmark
        # is publicly reachable and routing through a local proxy is never wanted.
        _session = requests.Session()
        _session.trust_env = False
        resp = _session.post(
            POSTMARK_API_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": POSTMARK_SERVER_TOKEN,
            },
            json={
                "From": SENDER_EMAIL,
                "To": recipient["email"],
                "Subject": subject,
                "HtmlBody": html_body,
                "TextBody": plain_body,
                "MessageStream": "outbound",
                "TrackOpens": True,
                "TrackLinks": "HtmlOnly",
            },
            timeout=30,
        )
        data = resp.json()
        if resp.status_code == 200 and data.get("ErrorCode") == 0:
            result["status"] = "sent"
            result["postmark_message_id"] = data.get("MessageID", "")
        else:
            result["status"] = "error"
            result["error_code"] = data.get("ErrorCode")
            result["error_message"] = data.get("Message", "")
    except Exception as e:
        result["status"] = "error"
        result["error_message"] = str(e)

    result["sent_at"] = datetime.now(timezone.utc).isoformat()
    return result


def save_to_db(results):
    from database.crm_db import upsert_contact, insert_email
    from database.db_config import get_connection

    conn = get_connection()
    added = 0
    for r in results:
        if r["status"] != "sent":
            continue
        upsert_contact(conn, r["email"], r.get("chair_name", ""), r.get("conference", ""))
        email_id = insert_email(
            conn, r["email"], r.get("postmark_message_id", ""),
            r.get("subject", ""), r.get("sent_at", ""),
            body_text=r.get("plain_body"),
            body_html=r.get("html_body"),
        )
        if email_id:
            added += 1
    conn.commit()
    conn.close()
    print(f"Database updated: {added} follow-up email(s) recorded")


def main():
    parser = argparse.ArgumentParser(description="Send follow-up emails as forwards to unreplied contacts")
    parser.add_argument("--send", action="store_true",
                        help="Actually send emails (without this flag, does a dry run)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit number of emails to send (0 = no limit)")
    parser.add_argument("--min-days", type=int, default=0,
                        help="Only follow up contacts whose first email was sent N+ days ago (0 = no minimum)")
    parser.add_argument("--template", default="followup-1.md",
                        help="Path to follow-up body template file")
    parser.add_argument("--test", action="store_true",
                        help="Use test database (crm_test) instead of production")
    args = parser.parse_args()

    if args.test:
        os.environ["USE_TEST_DB"] = "1"
        print("[TEST MODE] Using test database crm_test\n")

    if not POSTMARK_SERVER_TOKEN:
        print("ERROR: POSTMARK_SERVER_TOKEN not set in .env")
        sys.exit(1)

    body_template = load_followup_body(args.template)

    from database.db_config import get_connection
    from database.crm_db import get_followup_candidates

    conn = get_connection()
    candidates = get_followup_candidates(conn, min_days=args.min_days)
    conn.close()

    for c in candidates:
        c["first_name"] = extract_greeting_name(c["chair_name"])

    print(f"Found {len(candidates)} unreplied contact(s) eligible for follow-up")
    if args.min_days > 0:
        print(f"  (filtered to first email sent {args.min_days}+ days ago)")

    # Skip contacts whose original body was never stored / cannot be backfilled
    # (typically: sent > 45 days ago, before Postmark's retention window).
    # Forwarding them would require re-rendering the template, which is exactly
    # the drift problem we're fixing — so skipping is the safe choice.
    missing = [c for c in candidates if not c.get("body_text")]
    candidates = [c for c in candidates if c.get("body_text")]
    if missing:
        print(f"  SKIPPED {len(missing)} candidate(s) with no stored body "
              f"(run backfill_email_bodies.py to recover, or accept the loss):")
        for c in missing[:10]:
            print(f"    - {c['email']:35s}  {c['conference']:25s}  sent {c['sent_at']}")
        if len(missing) > 10:
            print(f"    ... and {len(missing)-10} more")

    if args.limit > 0:
        candidates = candidates[:args.limit]
        print(f"Limited to {len(candidates)} recipient(s)")

    if not candidates:
        print("No contacts to follow up. Done.")
        return

    dry_run = not args.send
    if dry_run:
        print("\n" + "=" * 60)
        print("  DRY RUN — no emails will be sent")
        print("  Add --send flag to actually send")
        print("=" * 60)

    print(f"\nSender: {SENDER_EMAIL}")
    print(f"Recipients: {len(candidates)}")
    print()

    results = []
    for i, r in enumerate(candidates):
        original_subject = r["subject"]
        fwd_subject = f"Fwd: {original_subject}"

        # follow-up note: still rendered from template (small, simple, only
        # needs first_name + conference, no platform).
        followup_text = render(body_template, r["conference"], r["first_name"])

        # original body: read from DB — exact bytes that were delivered.
        original_body = r["body_text"]

        plain_body = build_forwarded_body(
            followup_text, original_subject, original_body, SENDER_EMAIL
        )
        html_body = plain_to_html(plain_body)

        if i < 3 or dry_run:
            print(f"--- Follow-up {i+1} ---")
            print(f"  To:         {r['email']}")
            print(f"  Name:       {r['chair_name']}  (status: {r['status']})")
            print(f"  Conf:       {r['conference']}")
            print(f"  Subject:    {fwd_subject}")
            if i < 2:
                print(f"  Body:\n{plain_body}")
            print()

        result = send_forward(r, fwd_subject, plain_body, html_body, dry_run=dry_run)
        results.append(result)

        if not dry_run and i < len(candidates) - 1:
            time.sleep(0.5)

    sent = sum(1 for r in results if r["status"] == "sent")
    errors = sum(1 for r in results if r["status"] == "error")
    dry = sum(1 for r in results if r["status"] == "dry_run")

    print("=" * 60)
    if dry_run:
        print(f"DRY RUN complete: {dry} follow-up emails previewed")
        print("Run with --send to actually send")
    else:
        print(f"DONE: {sent} sent, {errors} errors")

    if not dry_run:
        save_to_db(results)


if __name__ == "__main__":
    main()
