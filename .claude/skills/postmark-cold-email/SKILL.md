---
name: postmark-cold-email
description: Send personalized cold emails via Postmark API using conference data. Use when the user wants to send outreach emails, cold emails, campaign emails, or asks about Postmark email sending.
---

# Postmark Cold Email Sender

## Overview

Send personalized cold outreach emails to conference chairs using Postmark's transactional email API. The user provides the data file and template at invocation time — nothing is hardcoded.

Safety rules (confirmation phrase, test-data handling, single-instance sending) live in the project's root `CLAUDE.md` — read that first, they are not repeated in full here.

## Prerequisites

- **Postmark API key**: `POSTMARK_SERVER_TOKEN` in `.env`
- **Sender email**: `POSTMARK_SENDER_EMAIL` in `.env` (defaults to `rain@paperfox.ai`; must be a verified sender/domain in Postmark)
- **Python packages**: `requests`, `python-dotenv`, `psycopg2`

## Data Source

The user specifies the recipient data file when invoking the skill. Supported formats:

| Format | Required columns |
|---|---|
| `.csv` | `conference_short_name`, `chair_name`, `chair_email` |
| `.json` | Same fields as CSV, as a list of objects |
| `.xlsx` | Name (col A), email (col B), Conference short name (col H) |

Only rows with a non-empty `chair_email` are eligible. Generic emails (`noreply@`, `admin@`, etc.) are filtered out during crawl-time validation (see `conference-crawling`), not re-validated here.

Recipients already present in the `contacts` table (i.e. already sent a first cold email — checked via `_get_already_sent_emails()`) are automatically skipped, so it's safe to hand the script the same crawl file repeatedly.

**Ask the user which data file to use if they don't specify one.**

## Email Template

`send_postmark.py --template <path>`, **default `email-template-v5.md`**. Template format: first line is `Subject: ...`, rest is the body. Available templates in the project root follow the pattern `email-template*.md` — ask the user which one if they haven't said, since v2/v3/v4/v5 have diverged wording.

Placeholders:

| Placeholder | Source field |
|---|---|
| `[Conference Name]` | `conference_short_name` |
| `[Name]` | Smart greeting via `extract_greeting_name`: "Prof./Dr. LastName" if a title is present in `chair_name`, otherwise first name, fallback "there" |
| `[Platform]` | `platform` field (defaults to "EasyChair" if absent) |

## Script Usage

```bash
# Dry run (always do this first)
python send_postmark.py <data_file> --template <template_file>

# With limit
python send_postmark.py <data_file> --template <template_file> --limit 50

# Actually send (requires user to say "Please send email")
python send_postmark.py <data_file> --template <template_file> --send

# Test mode (writes to crm_test database)
python send_postmark.py <data_file> --template <template_file> --test
```

## Workflow

### Step 1: Dry run (always do this first)

- [ ] Ask user for data file and template (if not specified)
- [ ] Run dry run: `python send_postmark.py <data_file> --template <template>`
- [ ] Show preview: count, sample subjects, sample bodies
- [ ] Wait for the user to say **"Please send email"** exactly

### Step 2: Send with confirmation

1. Run with `--send`
2. Emails are sent one by one with a 0.5s delay between sends
3. Each successful send is persisted to PostgreSQL **immediately** (not batched to the end of the loop) — see `save_email_result_to_db()` in `send_postmark.py`. This matters: a batched write would leave Postmark-delivered emails invisible to `_get_already_sent_emails()` if the process crashed mid-run, causing duplicate sends on the next run (this happened in production on 2026-04-21, affecting ~93 contacts, before the fix landed in commit `6c64227`).
4. Print summary: sent count, error count

### Step 3: Results logged to PostgreSQL

Send results are written directly via `database/crm_db.py` (`upsert_contact` + `insert_email`) to the `contacts` and `emails` tables — see `email-crm` skill for the full data model.

## Important Rules

1. **Never send without user confirmation** — see root `CLAUDE.md`
2. **Ask for file paths** — never assume which data file or template to use
3. **Use `--test` with test data** — see root `CLAUDE.md`
4. **Deduplicate** — same email address only ever receives one *first* cold email (enforced by the DB-backed skip logic, not by de-duping the input file — dedupe the input too if it's known to contain repeats)
5. **Skip bad emails** — this should already have happened at crawl time; `send_postmark.py` does not re-run email quality validation
6. **Log everything** — send results are saved directly to PostgreSQL, not to a local file

## Error Handling

| Postmark Error Code | Meaning | Action |
|---|---|---|
| 0 | Success | Log as sent |
| 300 | Invalid email | Skip, log as invalid |
| 406 | Inactive recipient | Skip, log as bounced |
| 429 | Rate limit | Wait 1s, retry once |
| Other | API error | Log error, continue |

## Related

- `first-follow-up` — forwards this email to unreplied recipients after a wait period
- `email-crm` — syncs delivery/open/click status back from Postmark after sending
