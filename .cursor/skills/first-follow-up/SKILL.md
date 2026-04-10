---
name: first-follow-up
description: Send first follow-up emails as forwards of the original outreach to unreplied contacts via Postmark API. Use when the user wants to follow up, re-engage unreplied contacts, send a first follow-up, or asks about following up on the email campaign.
---

# First Follow-Up Email Sender (Forward)

## Overview

Send a personalized follow-up to conference chairs who received the initial cold outreach but have not replied. The follow-up is sent **as a forward** of the original email — the recipient sees a new email with `Fwd:` in the subject and the original message quoted below a fresh introductory note.

## Prerequisites

- Initial campaign emails already sent (via `send_postmark.py`)
- CRM status synced at least once (`crm_check.py`) so delivery/bounce data is current
- **Postmark API key**: `POSTMARK_SERVER_TOKEN` in `.env`
- **Sender email**: `POSTMARK_SENDER_EMAIL` in `.env`
- **Python packages**: `requests`, `python-dotenv`, `psycopg2`

## How Forwarding Works

The script reads the original email's subject from the database, then:

- **Subject**: `Fwd: <original subject>` (e.g. `Fwd: Quick question about IFCS2026`)
- **Body**: New follow-up note on top, followed by `---------- Forwarded message ----------` and the rendered original email

No `In-Reply-To` or `References` headers are set — the follow-up arrives as a separate email, not in the original thread.

## Target Audience

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

Contacts who have already received a follow-up email are also excluded (deduplication via email count in DB).

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

### Step 1: Sync CRM status first

Before running follow-ups, ensure CRM data is current:

```bash
PYTHONUNBUFFERED=1 python crm_check.py
```

This updates delivery, open, click, and reply status so the candidate list is accurate.

### Step 2: Dry run (always do this first)

```bash
python send_followup.py --min-days 5
```

Review the output — it shows each contact's email, name, conference, the `Fwd:` subject, and a preview of the full body (follow-up note + forwarded original).

### Step 3: Send with explicit confirmation

**CRITICAL**: Only send if the user says exactly **"Please send email"**. "Send", "go ahead", "do it" is NOT sufficient.

```bash
python send_followup.py --send --min-days 5
```

### Step 4: Verify delivery

After sending, run a CRM check to sync delivery status for the follow-up emails:

```bash
PYTHONUNBUFFERED=1 python crm_check.py
```

## Important Rules

1. **Never send without explicit permission** — user must say "Please send email"
2. **Always dry run first** — show preview and get confirmation
3. **Sync CRM before follow-up** — ensures accurate candidate filtering
4. **No double follow-ups** — the script checks email count per contact to skip anyone who already received a follow-up
5. **Use --min-days in production** — recommended minimum of 3-5 days between initial email and follow-up
6. **All follow-ups are recorded** — new rows in the `emails` table, automatically tracked by existing CRM views
7. **Use `--test` with test data** — when testing, always add `--test` so results go to `crm_test`

## Data Flow

```
PostgreSQL (contact_status view)
  → get_followup_candidates() returns eligible contacts + original subject
  → send_followup.py renders follow-up note + original email body
  → Combines into Fwd: subject + forwarded message body
  → Postmark API sends email as a new forward
  → Result recorded in emails table
  → crm_check.py syncs delivery status
```
