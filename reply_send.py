#!/usr/bin/env python3
"""Send a genuine 1:1 reply that threads under the recipient's own message.

send_postmark.py and send_followup.py cannot do this. They compose fresh
campaign mail through Postmark: no In-Reply-To header, so the recipient sees a
new email rather than an answer to theirs, and the body gets Postmark's
click-tracking rewrites, which do not belong in a personal reply.

This sends over SMTP as the real mailbox instead. The reply threads correctly,
carries no tracking, lands in Sent, and is recorded in `conversations` so the
CRM does not later think the person was ignored.

    # find her message and preview the reply (default: nothing is sent)
    python3 reply_send.py --to chair@example.edu --body-file draft.txt

    # actually send it
    python3 reply_send.py --to chair@example.edu --body-file draft.txt --send
"""

import argparse
import email as email_lib
import imaplib
import os
import smtplib
import ssl
import sys
import time
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv(Path(__file__).parent / ".env")

IMAP_SERVER = os.getenv("IMAP_SERVER", "mail.privateemail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
SMTP_SERVER = os.getenv("SMTP_SERVER", "mail.privateemail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
# Same fallback chain crm_check.py uses: EMAIL_ADDRESS is not set in .env on
# this machine, the mailbox is the Postmark sender address.
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS") or os.getenv("POSTMARK_SENDER_EMAIL")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SENDER_NAME = os.getenv("SENDER_NAME", "Rain Jiang")


def is_ascii(value):
    try:
        (value or "").encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def unfold(value):
    """Collapse RFC 5322 folding whitespace into single spaces.

    A long Message-ID arrives from IMAP split across lines, and feeding that
    straight back into a header raises "Header values may not contain linefeed
    or carriage return characters" — so threading breaks on exactly the long
    ids that Exchange and Outlook generate.
    """
    return " ".join(value.split()) if value else value


def find_their_message(to_addr):
    """Return (message_id, references, subject, date) of their latest message to us.

    Threading needs the exact Message-ID they sent, which is not stored in the
    database — conversations.postmark_message_id only ever holds our own
    outbound ids — so it has to come from the mailbox.
    """
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    try:
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("INBOX")
        status, data = mail.search(None, f'(FROM "{to_addr}")')
        if status != "OK" or not data[0].split():
            return None
        latest = data[0].split()[-1]
        status, fetched = mail.fetch(
            latest,
            "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID SUBJECT DATE REFERENCES)])",
        )
        msg = email_lib.message_from_bytes(fetched[0][1])
        return (unfold(msg.get("Message-ID")), unfold(msg.get("References")),
                unfold(msg.get("Subject")), unfold(msg.get("Date")))
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def check_suppression(to_addr):
    """opt_out is an absolute block. Other reasons only warn: someone who
    declined a pitch but then wrote to us still deserves an answer."""
    from database.db_config import get_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT reason, note FROM suppressions WHERE email = LOWER(%s)",
                    (to_addr,))
        return cur.fetchone()
    finally:
        conn.close()


def record_in_conversations(to_addr, subject, body, sent_at):
    from database.db_config import get_connection
    from database.crm_db import insert_conversation
    conn = get_connection()
    try:
        ok = insert_conversation(conn, contact_email=to_addr, direction="outbound",
                                 subject=subject, body_text=body, message_at=sent_at)
        conn.commit()
        return ok
    finally:
        conn.close()


def append_to_sent(raw_bytes):
    """Put a copy in Sent, so the reply is visible in the mail client."""
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    try:
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        for folder in ("Sent", "INBOX.Sent", "Sent Items", "INBOX.Sent Items"):
            try:
                if mail.append(folder, "\\Seen",
                               imaplib.Time2Internaldate(time.time()),
                               raw_bytes)[0] == "OK":
                    return folder
            except Exception:
                continue
        return None
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description="Send a threaded 1:1 reply over SMTP")
    ap.add_argument("--to", required=True)
    ap.add_argument("--body-file", required=True, help="plain-text body")
    ap.add_argument("--subject", help="default: Re: <their subject>")
    ap.add_argument("--in-reply-to", help="override the auto-detected Message-ID")
    ap.add_argument("--send", action="store_true",
                    help="actually send (without this, previews only)")
    args = ap.parse_args()

    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        sys.exit("EMAIL_ADDRESS / EMAIL_PASSWORD not configured")

    to_addr = parseaddr(args.to)[1].lower()
    body = Path(args.body_file).read_text().rstrip() + "\n"

    sup = check_suppression(to_addr)
    if sup:
        reason, note = sup
        if reason == "opt_out":
            sys.exit(f"REFUSING: {to_addr} is on the never-send list (opt_out) — {note}")
        print(f"NOTE: {to_addr} is suppressed as '{reason}' ({note}).")
        print("      Replying to a message they sent us is still fine; continuing.\n")

    found = None if args.in_reply_to else find_their_message(to_addr)
    if args.in_reply_to:
        their_id, their_refs, their_subj = args.in_reply_to, None, None
    elif found:
        their_id, their_refs, their_subj, their_date = found
        print(f"Their message: {their_date}")
        print(f"  Subject:    {their_subj}")
        print(f"  Message-ID: {their_id}")
    else:
        sys.exit(f"No message from {to_addr} found in INBOX — pass --in-reply-to "
                 f"with their Message-ID to reply anyway.")

    subject = args.subject or their_subj or "(no subject)"
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    # MIMEText (compat32), not EmailMessage. EmailMessage's default policy does
    # not register in-reply-to/references as msg-id headers, so it treats them
    # as free text: a Message-ID longer than the 78-column fold limit has no
    # whitespace to fold at, and the policy falls back to RFC 2047 encoded-words
    # (=?utf-8?q?=3C...?=). An encoded-word in In-Reply-To is not a msg-id, so
    # the reply silently stops threading. Exchange and Outlook routinely emit
    # ids past that length, which is most of academia. compat32 passes ASCII
    # header values through untouched.
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = f"{SENDER_NAME} <{EMAIL_ADDRESS}>"
    msg["To"] = to_addr
    msg["Subject"] = (subject if is_ascii(subject)
                      else Header(subject, "utf-8").encode())
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=EMAIL_ADDRESS.split("@")[-1])
    if their_id:
        msg["In-Reply-To"] = their_id
        # Chain their References plus their own id, so clients that build the
        # thread from References (not just In-Reply-To) also get it right.
        msg["References"] = " ".join(filter(None, [their_refs, their_id]))

    print("\n" + "=" * 62)
    print("  DRY RUN — nothing sent" if not args.send else "  SENDING")
    print("=" * 62)
    for h in ("From", "To", "Subject", "In-Reply-To", "References"):
        if msg[h]:
            print(f"{h+':':<14}{msg[h]}")
    print("-" * 62)
    print(body)
    print("=" * 62)

    if not args.send:
        print("\nAdd --send to actually send this.")
        return

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30,
                          context=ssl.create_default_context()) as s:
        s.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        s.send_message(msg)
    print(f"\nSENT to {to_addr}")

    folder = append_to_sent(msg.as_bytes())
    print(f"Copied to '{folder}'" if folder else "WARNING: could not copy to Sent")

    if record_in_conversations(to_addr, subject, body,
                               time.strftime("%Y-%m-%d %H:%M:%S")):
        print("Recorded in conversations.")
    else:
        print("WARNING: not recorded in conversations (contact may not exist).")


if __name__ == "__main__":
    main()
