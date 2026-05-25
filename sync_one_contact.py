#!/usr/bin/env python3
"""Focused IMAP sync for a single contact's email exchange.

Fetches every inbound + outbound message between us and the given contact
from IMAP (INBOX and Sent), and writes them to the conversations table.
Also calls insert_reply for new inbound messages so the contact's status
in contact_status stays accurate.

Usage:
    python sync_one_contact.py <email>
"""

import argparse
import email as email_lib
import imaplib
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from crm_check import (  # noqa: E402  reuse existing helpers
    decode_mime_header,
    extract_email_address,
    get_email_body,
    is_auto_reply,
    parse_email_date,
)
from database.crm_db import insert_conversation, insert_reply  # noqa: E402
from database.db_config import get_connection  # noqa: E402

IMAP_SERVER = os.getenv("IMAP_SERVER", "mail.privateemail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS") or os.getenv("POSTMARK_SENDER_EMAIL")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")


def _fetch_messages(mail, folder: str, search_criteria: str):
    """Select `folder` and yield parsed email.Message objects matching `search_criteria`."""
    status, _ = mail.select(folder)
    if status != "OK":
        print(f"  ! Could not select folder {folder!r}")
        return
    status, data = mail.search(None, search_criteria)
    if status != "OK":
        print(f"  ! IMAP search failed in {folder!r}: {search_criteria}")
        return
    ids = data[0].split()
    print(f"  {folder}: matched {len(ids)} message(s)")
    for eid in ids:
        st, msg_data = mail.fetch(eid, "(RFC822)")
        if st != "OK" or not msg_data:
            continue
        raw = msg_data[0][1]
        yield email_lib.message_from_bytes(raw)


def _resolve_sent_folder(mail) -> str:
    """Try common Sent folder names; return the one IMAP accepts."""
    for candidate in ("Sent", "INBOX.Sent", '"Sent Items"', '"[Gmail]/Sent Mail"'):
        st, _ = mail.select(candidate)
        if st == "OK":
            return candidate
    return "Sent"


def sync_contact(target_email: str) -> None:
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        sys.exit("EMAIL_ADDRESS / EMAIL_PASSWORD must be set in .env")

    target = target_email.strip().lower()
    print(f"Syncing exchange with: {target}\n")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, subject, sent_at FROM emails WHERE contact_email = %s ORDER BY sent_at ASC LIMIT 1",
        (target,),
    )
    row = cur.fetchone()
    cur.close()
    original_email_id = row[0] if row else None
    if original_email_id:
        print(f"  Original outbound email_id={original_email_id}")
    else:
        print("  ⚠ No prior outbound email found in DB; replies won't be linked via email_id.")
    print()

    print(f"Connecting to {IMAP_SERVER}…")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    print("  connected.\n")

    inbound_inserted = 0
    outbound_inserted = 0
    new_replies = 0

    print("→ INBOX (inbound from contact):")
    inbox_criteria = f'(FROM "{target}")'
    for msg in _fetch_messages(mail, "INBOX", inbox_criteria):
        from_header = decode_mime_header(msg.get("From", ""))
        from_email = extract_email_address(from_header)
        if from_email != target:
            continue
        subject = decode_mime_header(msg.get("Subject", ""))
        if is_auto_reply(subject):
            print(f"    ↪ skip auto-reply: {subject[:60]}")
            continue
        date_str = msg.get("Date", "")
        parsed_dt = parse_email_date(date_str)
        msg_at_iso = parsed_dt.isoformat() if parsed_dt else date_str
        body = get_email_body(msg)

        cid = insert_conversation(
            conn, target, "inbound", subject, body, msg_at_iso,
        )
        if cid:
            inbound_inserted += 1
            print(f"    + conv #{cid}  {msg_at_iso[:19]}  '{subject[:55]}'")
        else:
            print(f"    = dedup     {msg_at_iso[:19]}  '{subject[:55]}'")

        if original_email_id:
            rid = insert_reply(conn, original_email_id, date_str, body, False)
            if rid:
                new_replies += 1
                print(f"      → also inserted reply #{rid} (needs classification)")

    print()
    print("→ Sent (outbound to contact):")
    sent_folder = _resolve_sent_folder(mail)
    sent_criteria = f'(TO "{target}")'
    for msg in _fetch_messages(mail, sent_folder, sent_criteria):
        to_headers = " ".join([
            decode_mime_header(msg.get(h, "") or "") for h in ("To", "Cc", "Bcc")
        ])
        if target not in to_headers.lower():
            continue
        subject = decode_mime_header(msg.get("Subject", ""))
        date_str = msg.get("Date", "")
        parsed_dt = parse_email_date(date_str)
        msg_at_iso = parsed_dt.isoformat() if parsed_dt else date_str
        body = get_email_body(msg)

        cid = insert_conversation(
            conn, target, "outbound", subject, body, msg_at_iso,
        )
        if cid:
            outbound_inserted += 1
            print(f"    + conv #{cid}  {msg_at_iso[:19]}  '{subject[:55]}'")
        else:
            print(f"    = dedup     {msg_at_iso[:19]}  '{subject[:55]}'")

    conn.commit()
    mail.logout()
    conn.close()

    print()
    print("=" * 60)
    print(f"  inbound inserted:  {inbound_inserted}")
    print(f"  outbound inserted: {outbound_inserted}")
    print(f"  new replies rows:  {new_replies}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("email", help="Contact email to sync")
    args = parser.parse_args()
    sync_contact(args.email)


if __name__ == "__main__":
    main()
