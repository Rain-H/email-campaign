---
name: email-crm
description: Track email campaign status through full lifecycle via Postmark API, IMAP replies, and Claude AI classification. Use when the user wants to check email status, track delivery, detect replies, classify responses, generate CRM reports, or reconcile the sent/unsent contact list.
---

# Email CRM Status Tracker

## Overview

Tracks every sent cold email through its full lifecycle:
`sent -> delivered/bounced -> clicked -> replied -> AI classified`

All state is stored in PostgreSQL (via `database/crm_db.py`). Optional `--export-json` flag exports to `crm.json`.

**The database, not Postmark, is the durable source of truth.** Postmark only retains outbound message activity/content for ~45 days (confirmed 2026-07-24 — see the retention gotcha below). Anything sent longer ago than that cannot be recovered from Postmark; the `emails` table is all that's left.

## Signal Reliability

- **Delivered / Bounced** — Postmark delivery confirmation. Very reliable.
- **Link clicked** — Postmark `TrackLinks` rewrites links into tracked redirects. Requires intentional human action, cannot be faked by bots. **Primary engagement signal.**
- **Replied** — IMAP detection of reply emails. Reliable when matched correctly.
- **Opened (pixel)** — Postmark tracking pixel. **Unreliable.** False positives from mail scanners (QQ Mail, university gateways auto-fetching images) and false negatives from privacy-blocking clients (Gmail, Apple Mail). Kept as approximate/supplementary signal only.

## Prerequisites

- `POSTMARK_SERVER_TOKEN` in `.env` (delivery/open/click tracking)
- `EMAIL_ADDRESS` and `EMAIL_PASSWORD` in `.env` (IMAP reply detection)
- `ANTHROPIC_API_KEY` in `.env` (reply classification)
- Python packages: `requests`, `python-dotenv`, `anthropic`, `psycopg2`

## Postmark Server Settings

- `TrackOpens: true` — injects tracking pixel (supplementary signal only)
- `TrackLinks: HtmlOnly` — rewrites links for click tracking (primary engagement signal)
- The HTML body sent to Postmark must include `<html><body>...</body></html>` tags, or Postmark can't inject the tracking pixel.

## Postmark gotchas (learned the hard way — verify before trusting a Postmark query)

1. **Shared account, mixed traffic.** This Postmark server also sends PaperFox product notifications (`notifications@paperfox.ai` — e.g. "Review Submitted"). As of 2026-07-24 those made up ~12,450 of ~12,476 total outbound messages on the account. Cold-campaign emails come from `rain@paperfox.ai`. Always filter by `fromemail`/sender, or by the tracked `postmark_message_id`s already in the DB — never treat "total messages on the account" as "our campaign volume."
2. **45-day retention.** Postmark drops outbound message activity and content after ~45 days. A message from 2026-05-19 (66 days old at the time) returned `422 {"ErrorCode":701,"Message":"This message was not found."}` from `/messages/outbound/{id}/details`. If you need to reconcile against something older than that, Postmark can't help — fall back to the `emails` table's own timestamps and duplicate-detection (see "Internal reconciliation" below).
3. **`fromemail` param works for bulk search** — confirmed via `/messages/outbound?fromemail=...`, returns `TotalCount` scoped to that sender.

## Data Model (PostgreSQL)

Four tables: `contacts`, `emails`, `replies`, `conversations`. Status is computed by the `contact_status` view. Full schema in `database/schema.sql`.

- `contacts` — one row per recipient email (`email` PK, `name`, `conference`, `source_platform`)
- `emails` — one row per email actually sent (`contact_email`, `postmark_message_id`, `subject`, `body_text`/`body_html`, `sent_at`, delivery/bounce/open/click timestamps). A contact with 2 rows here has received a first email + one follow-up (the follow-up subject is always prefixed `Fwd: `, see `first-follow-up`).
- `replies` — one row per detected reply (`is_interested`, AI classification confidence/reasoning), FK to `emails.id`
- `conversations` — full outbound+inbound thread log (`direction`, `message_at`, `thread_order`), populated by `sync_emails_to_conversations()` / `sync_replies_to_conversations()`; used by `weekly-stats` for engagement metrics

## Status Values (`contact_status` view)

- `replied_interested` — replied, AI classified as interested
- `replied_not_interested` — replied, AI classified as not interested
- `clicked_no_reply` — clicked a link but hasn't replied
- `opened_no_reply` — opened but hasn't clicked or replied (unreliable signal)
- `no_reply` — delivered but no engagement detected
- `failed` — bounced/spam

## Postmark Sync: bulk mode (default) vs per-contact mode

`crm_check.py` syncs Postmark status two ways:

- **Bulk mode (default)** — paginates `/messages/outbound`, `/bounces`, `/messages/outbound/opens`, `/messages/outbound/clicks` at up to 500 records/page, matches results against tracked `postmark_message_id`s in memory. A handful of requests instead of 3 API calls × N contacts. Defaults `--from-date` to 120 days back if not given (this is a safe-but-loose default — Postmark won't actually have anything past ~45 days regardless, so the effective window is always ≤45 days).
- **Per-contact mode (`--per-contact`)** — the old N-calls-per-contact path. Much slower; only use it if bulk mode is misbehaving. Supports `--start-from` (resume index) and `--commit-every` (checkpoint interval).

## Reply Detection (IMAP)

Connects to `mail.privateemail.com` via IMAP and searches for replies to campaign emails.

**Matching rules (all must pass):**

1. `In-Reply-To` / `References` headers against sent Postmark `Message-ID`s (standard reply detection)
2. Fallback: match by exact campaign subject line
3. Sender email must be in the CRM contact list
4. Reply date must be AFTER the campaign `sent_at` timestamp

**Do NOT use broad keyword search** (e.g. "EasyChair", "PaperFox") — matches unrelated inbox emails and produces false positives.

## AI Classification

Claude classifies replies into `interested` or `rejected` (stored as `is_interested` boolean).

## Usage

```bash
# Full sync (Postmark + replies + classify + conversations), bulk mode by default
python3 crm_check.py

# Only check Postmark status
python3 crm_check.py --postmark-only

# Only check replies (IMAP + classify + sync)
python3 crm_check.py --replies-only

# Show report without syncing
python3 crm_check.py --report

# Export DB to crm.json
python3 crm_check.py --export-json

# Force slow per-contact Postmark sync instead of bulk
python3 crm_check.py --per-contact --start-from 0 --commit-every 50

# Limit bulk Postmark queries to a date range
python3 crm_check.py --from-date 2026-06-01

# Test mode (crm_test database)
python3 crm_check.py --test
```

`send_postmark.py` and `send_followup.py` write directly to PostgreSQL on send — no separate ingestion step needed.

## Internal reconciliation (when Postmark's data has aged out)

Since Postmark can't confirm sends older than ~45 days, sanity-check the `emails` table directly for signs of the double-send bug fixed in commit `6c64227` (pre-fix: DB write only happened after the whole send loop finished, so a mid-run crash could leave a Postmark-delivered email un-recorded, and it would look "unsent" and get resent):

```sql
WITH ranked AS (
  SELECT contact_email, subject, sent_at,
         ROW_NUMBER() OVER (PARTITION BY contact_email ORDER BY sent_at) rn,
         COUNT(*) OVER (PARTITION BY contact_email) cnt
  FROM emails
),
pairs AS (
  SELECT a.contact_email, a.subject s1, b.subject s2, a.sent_at t1, b.sent_at t2,
         EXTRACT(EPOCH FROM (b.sent_at - a.sent_at))/60 gap_min
  FROM ranked a JOIN ranked b ON a.contact_email=b.contact_email AND a.rn=1 AND b.rn=2
  WHERE a.cnt = 2
)
SELECT COUNT(*) FILTER (WHERE s1=s2 AND gap_min < 60) AS likely_double_send,
       COUNT(*) FILTER (WHERE s1<>s2) AS legit_followup   -- follow-up subject is always "Fwd: <original>", never identical
FROM pairs;
```

A real legitimate follow-up (see `first-follow-up`) always has subject `Fwd: <original subject>` and is sent 3-5+ days later, per that skill's `--min-days` recommendation — so `s1=s2` with a sub-hour gap is never a follow-up, it's the bug. (Verified against `send_followup.py`: the `Fwd: ` prefix has been in every commit since the file's `Initial commit`, 2026-04-10.)

## Related unsent-list check

`check_unsent_chairs.py` merges all `crawled_easychair_*.csv` / `crawled_edas_*.csv` files, dedupes by email, and diffs against `SELECT DISTINCT LOWER(email) FROM contacts` to find candidates who've never been sent a first cold email. Writes the result to `unsent_chairs.csv`. This is the DB-only check — it cannot detect the double-send scenario above (that needs the `emails` table query, not `contacts`).

## Output

```
FUNNEL:
  Sent:      10
  Delivered: 9   (90%)
  Bounced:   1   (10%)
  Clicked:   3   (30%)    <-- primary engagement signal
  Replied:   2   (20%)
  Opened:    ~5  (approx, pixel-based, unreliable)

CONTACTS (10 total)
  Name             Email                    Conference    Status
  Felix Ramos      felix@cinvestav.mx       BICA 2026     clicked
  ...
```
