---
name: first-follow-up
description: Send first follow-up emails as forwards of the original outreach to unreplied contacts via Postmark API. Use when the user wants to follow up, re-engage unreplied contacts, send a first follow-up, or asks about following up on the email campaign.
---

# First Follow-Up Email Sender (Forward)

## Overview

Send a personalized follow-up to conference chairs who received the initial cold outreach but have not replied. The follow-up is sent **as a forward** of the original email — the recipient sees a new email with `Fwd:` in the subject and the original message quoted below a fresh introductory note.

## Prerequisites

- Initial campaign emails already sent (via `send_postmark.py`)
- PostgreSQL CRM database is the **single source of truth** — candidate selection reads `contact_status` view directly; do not query Postmark for eligibility
- The database is assumed to be reasonably fresh (synced on a separate routine by `crm_check.py`); no on-demand sync is required as part of this workflow
- **Postmark API key**: `POSTMARK_SERVER_TOKEN` in `.env` (used only to send the follow-up, not to select recipients)
- **Sender email**: `POSTMARK_SENDER_EMAIL` in `.env`
- **Python packages**: `requests`, `python-dotenv`, `psycopg2`

## How Forwarding Works

The script reads the original email's subject from the database, then:

- **Subject**: `Fwd: <original subject>` (e.g. `Fwd: Quick question about IFCS2026`)
- **Body**: New follow-up note on top, followed by `---------- Forwarded message ----------` and the rendered original email

No `In-Reply-To` or `References` headers are set — the follow-up arrives as a separate email, not in the original thread.

## Target Audience

Eligibility is computed **entirely from the database** (`contact_status` view + `emails` table). The script does not consult Postmark to decide who to follow up with.

Contacts with these statuses are eligible for follow-up:

| Status | Meaning |
|---|---|
| `no_reply` | Delivered, no opens, no reply |
| `opened_no_reply` | Opened at least once, no reply |
| `clicked_no_reply` | Clicked a link, no reply |

Contacts with these statuses are **excluded**:

| Status | Reason |
|---|---|
| `failed` (bounced) | Email didn't reach them |
| `replied_interested` | Already engaged |
| `replied_not_interested` | Already declined |

Contacts who have already received a follow-up email are also excluded (deduplication via email count in DB: `(SELECT COUNT(*) FROM emails WHERE contact_email = cs.email) = 1`).

## Email Templates

Two templates are used:

1. **Follow-up note** (`--template`, defaults to `followup-1.md`): The new introductory text placed above the forwarded content. Contains **only the body** (no Subject line).
2. **Original email** (`--original-template`, defaults to `email-template-v2.md`): The original outreach template whose rendered body is included below the `---------- Forwarded message ----------` separator.

Placeholders (both templates):

| Placeholder | Source |
|---|---|
| `[Conference Name]` | `conference` from DB |
| `[Name]` | Smart greeting via `extract_greeting_name` |

**Ask the user which templates to use if they want different ones.** Follow-up templates in the project root have the pattern `followup-*.md`.

## Script Usage

The sending script is `send_followup.py`.

```bash
# Dry run (default) — preview all eligible follow-ups
python send_followup.py

# Dry run with limit
python send_followup.py --limit 10

# Only follow up contacts whose first email was sent 5+ days ago
python send_followup.py --min-days 5

# Actually send (requires user to say "Please send email")
python send_followup.py --send

# Combine options
python send_followup.py --send --min-days 5 --limit 50

# Use different templates
python send_followup.py --template <followup_template> --original-template <original_template>

# Test mode (writes to crm_test database)
python send_followup.py --test
```

## Workflow

### Step 1: Dry run from the database (always do this first)

Candidate selection is read straight from the database — no Postmark fetch is required here. Assume the user keeps the DB fresh via their own routine.

```bash
python send_followup.py --min-days 5
```

Review the output — it shows each contact's email, name, conference, the `Fwd:` subject, and a preview of the full body (follow-up note + forwarded original). All rows come from the `contact_status` view.

> If the user explicitly asks to refresh first (e.g. "the DB might be stale"), run `PYTHONUNBUFFERED=1 python crm_check.py` once and then re-run the dry run. Do not do this by default.

### Step 2: Send with explicit confirmation

**CRITICAL**: Only send if the user says exactly **"Please send email"**. "Send", "go ahead", "do it" is NOT sufficient.

```bash
python send_followup.py --send --min-days 5
```

Each successful send is written to the `emails` table immediately (via `insert_email` in `database/crm_db.py`), so the next follow-up run will automatically skip these contacts (their `COUNT(*) FROM emails > 1`).

### Step 3: (Optional) Verify delivery later

Delivery, open, click, and bounce status for the new follow-up rows are filled in by the user's regular `crm_check.py` runs. There is no need to run it immediately after sending unless the user specifically asks for an up-to-the-minute report.

## Important Rules

1. **Never send without explicit permission** — user must say "Please send email"
2. **Always dry run first** — show preview and get confirmation
3. **Database is the source of truth** — eligibility is decided by the `contact_status` view + `emails` table, never by querying Postmark. Do not insert a `crm_check.py` step into this workflow unless the user explicitly asks for a fresh sync.
4. **No double follow-ups** — the script checks email count per contact to skip anyone who already received a follow-up
5. **Use --min-days in production** — recommended minimum of 3-5 days between initial email and follow-up
6. **All follow-ups are recorded** — new rows in the `emails` table, automatically tracked by existing CRM views
7. **Use `--test` with test data** — when testing, always add `--test` so results go to `crm_test`

## Data Flow

```
PostgreSQL  (single source of truth for eligibility)
  ├── contact_status view  ── status, sent_at, replied_at, bounced_at, original subject
  └── emails table         ── COUNT(*) per contact (excludes anyone already followed up)
        │
        ▼
  get_followup_candidates(conn, min_days=N)   ← pure DB query, no Postmark call
        │
        ▼
  send_followup.py renders follow-up note + forwarded original body
        │
        ▼
  Postmark API  ← used ONLY to send the email (not to select recipients)
        │
        ▼
  insert_email() writes the new send back to PostgreSQL.emails
        │
        ▼
  (Out of band)  user's routine crm_check.py later fills in delivered_at / opened_at / replies
```
