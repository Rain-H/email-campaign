#!/usr/bin/env python3
"""Manage the never-send list.

Any address in `suppressions` is blocked by send_postmark.py and
send_followup.py before a message is composed, whether or not it is a known
contact — so an address can be suppressed before it is ever crawled.

    python3 suppress.py --add chair@example.edu --reason opt_out --note "asked to stop, 2026-08-07"
    python3 suppress.py --list
    python3 suppress.py --check chair@example.edu
    python3 suppress.py --scan            # find opt-out language in stored replies
    python3 suppress.py --scan --apply    # ...and suppress the unambiguous ones

Reasons:
    opt_out   explicitly asked us to stop. Never send, no exceptions.
    declined  explicitly said they are not interested.
    manual    added by hand; put the why in --note.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database.db_config import get_connection
from database.crm_db import add_suppression, is_suppressed

REASONS = ("opt_out", "declined", "manual")

# Phrases that are a request to stop being contacted. Deliberately narrow:
# a false positive here silently deletes a prospect, so borderline wording
# ("we already use EasyChair") is left for a human to judge via --scan output.
OPT_OUT_RE = re.compile(
    r"(stop sending|stop email|stop contact|stop mailing|unsubscribe|remove me|"
    r"take me off|opt.?out|do not (email|contact|send|write)|"
    r"don'?t (email|contact|send|write)|no longer wish|leave me alone|"
    r"stop bothering|never contact)",
    re.I,
)
DECLINE_RE = re.compile(
    r"(i am not interested|i'm not interested|not interested, |not interested\.|"
    r"no interest thank|we are not interested|we're not interested)",
    re.I,
)
# Vacation responders quote our own mail back and can contain anything; they
# are not opinions and must never be treated as a decline.
AUTO_RE = re.compile(
    r"(out of (the )?office|on vacation|on leave|automatic reply|auto.?reply|"
    r"currently away|will return|annual leave|maternity|parental leave)",
    re.I,
)


def reply_body(text: str) -> str:
    """Strip the quoted original so we match what THEY wrote, not what we did."""
    t = (text or "").lower()
    for marker in ("---------- forwarded", "wrote:", "-----original message"):
        t = t.split(marker)[0]
    return t[:1200]


def cmd_add(conn, email, reason, note):
    if reason not in REASONS:
        raise SystemExit(f"--reason must be one of {', '.join(REASONS)}")
    added = add_suppression(conn, email, reason, note, source="suppress.py")
    conn.commit()
    if added:
        print(f"suppressed: {email.lower()}  ({reason})")
    else:
        print(f"already suppressed: {email.lower()} — existing entry left unchanged")


def cmd_list(conn):
    cur = conn.cursor()
    cur.execute("""SELECT email, reason, note, created_at FROM suppressions
                   ORDER BY reason, email""")
    rows = cur.fetchall()
    if not rows:
        print("suppression list is empty")
        return
    print(f"{len(rows)} suppressed address(es):\n")
    print(f"  {'EMAIL':<42}{'REASON':<11}{'ADDED':<12}NOTE")
    for email, reason, note, created in rows:
        print(f"  {email:<42}{reason:<11}{str(created)[:10]:<12}{note or ''}")


def cmd_check(conn, email):
    print(f"{email}: {'SUPPRESSED' if is_suppressed(conn, email) else 'not suppressed'}")


def cmd_scan(conn, apply_changes):
    cur = conn.cursor()
    cur.execute("""SELECT e.contact_email, c.name, c.conference, r.full_content
                   FROM replies r
                   JOIN emails e ON e.id = r.email_id
                   JOIN contacts c ON c.email = e.contact_email""")
    opt_outs, declines = [], []
    for email, name, conf, content in cur.fetchall():
        body = reply_body(content)
        if OPT_OUT_RE.search(body):
            opt_outs.append((email, name, conf, OPT_OUT_RE.search(body).group(0), body))
        elif DECLINE_RE.search(body) and not AUTO_RE.search(body):
            declines.append((email, name, conf, DECLINE_RE.search(body).group(0), body))

    for label, reason, group in (("OPT-OUT", "opt_out", opt_outs),
                                 ("DECLINED", "declined", declines)):
        print(f"\n=== {label} ({len(group)}) ===")
        for email, name, conf, matched, body in group:
            already = is_suppressed(conn, email)
            mark = "already suppressed" if already else ("SUPPRESSING" if apply_changes else "would suppress")
            print(f"\n  {email}  [{name} · {conf}]  -> {mark}")
            print(f"    matched: \"{matched}\"")
            print(f"    said:    {body.strip()[:160]}")
            if apply_changes and not already:
                add_suppression(conn, email, reason,
                                note=f'reply matched "{matched}"', source="suppress.py --scan")
    if apply_changes:
        conn.commit()
        print("\ncommitted.")
    else:
        print("\n(dry run — re-run with --apply to write these)")


def main():
    ap = argparse.ArgumentParser(description="Manage the never-send list")
    ap.add_argument("--add", metavar="EMAIL")
    ap.add_argument("--reason", default="manual", help=f"one of: {', '.join(REASONS)}")
    ap.add_argument("--note")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check", metavar="EMAIL")
    ap.add_argument("--scan", action="store_true",
                    help="find opt-out language in stored replies")
    ap.add_argument("--apply", action="store_true",
                    help="with --scan, actually write the suppressions")
    ap.add_argument("--test", action="store_true", help="use crm_test")
    args = ap.parse_args()

    conn = get_connection(use_test_db=args.test)
    try:
        if args.add:
            cmd_add(conn, args.add, args.reason, args.note)
        elif args.check:
            cmd_check(conn, args.check)
        elif args.scan:
            cmd_scan(conn, args.apply)
        elif args.list:
            cmd_list(conn)
        else:
            ap.print_help()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
