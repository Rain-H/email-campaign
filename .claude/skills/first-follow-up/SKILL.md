---
name: first-follow-up
description: Send first follow-up emails as forwards of the original outreach to unreplied contacts via Postmark API. Use when the user wants to follow up, re-engage unreplied contacts, send a first follow-up, or asks about following up on the email campaign.
---

# First Follow-Up Email Sender (Forward)

## Overview

Send a personalized follow-up to conference chairs who received the initial cold outreach but have not replied. The follow-up is sent **as a forward** of the original email — the recipient sees a new email with `Fwd:` in the subject and the original message quoted below a fresh introductory note.

Safety rules (confirmation phrase, test-data handling) live in the project's root `CLAUDE.md`.

## Prerequisites

- Initial campaign emails already sent (via `send_postmark.py` — see `postmark-cold-email`)
- PostgreSQL CRM database is the **single source of truth** — candidate selection reads `contact_status` view + `emails` table directly; do not query Postmark for eligibility
- The database is assumed to be reasonably fresh (synced separately by `crm_check.py` — see `email-crm`); no on-demand sync is required as part of this workflow
- **Postmark API key**: `POSTMARK_SERVER_TOKEN` in `.env` (used only to send the follow-up, not to select recipients)
- **Sender email**: `POSTMARK_SENDER_EMAIL` in `.env`
- **Python packages**: `requests`, `python-dotenv`, `psycopg2`

## How Forwarding Works

The script reads the **original email's stored body** (`emails.body_text` / `body_html` — the exact bytes actually delivered, not a re-render of the template) and:

- **Subject**: `Fwd: <original subject>` (e.g. `Fwd: Quick question about IFCS2026`) — this prefix has been in the code since the very first commit of `send_followup.py` (2026-04-10) and is never omitted; a follow-up subject is never identical to the original.
- **Body**: new follow-up note on top, followed by `---------- Forwarded message ----------` and the original email

No `In-Reply-To` or `References` headers are set — the follow-up arrives as a separate email, not threaded.

Re-rendering the original template at follow-up time is deliberately avoided: templates, `[Platform]` defaults, and conference naming all drift over time, so the forwarded content could stop matching what the recipient actually received. If a contact's original body was never stored (typically: sent >45 days ago, before Postmark's retention window closed, or before body-storage was added to the send path), they're **skipped** — run `backfill_email_bodies.py` first to try to recover it from Postmark (only works within the ~45-day window), or accept the loss.

## Target Audience

Eligibility is computed **entirely from the database** (`contact_status` view + `emails` table). The script does not consult Postmark to decide who to follow up with.

Eligible statuses: `no_reply`, `opened_no_reply`, `clicked_no_reply` (delivered, not replied — opened/clicked doesn't disqualify).

Excluded: `failed` (bounced — never reached them), `replied_interested`, `replied_not_interested` (already engaged/declined).

Contacts who've already received a follow-up are also excluded — deduplication via `(SELECT COUNT(*) FROM emails WHERE contact_email = cs.email) = 1` (i.e. only exactly one prior send).

## Email Templates

Two templates:

1. **Follow-up note** (`--template`, default `followup-1.md`): the new introductory text above the forwarded content. Body only, no Subject line.
2. **Original email** (`--original-template`, default `email-template-v2.md`): used only to render `[Conference Name]`/`[Name]` for the *new* note, not to reconstruct the forwarded original (that comes verbatim from the DB).

Placeholders: `[Conference Name]` from DB `conference`, `[Name]` via smart greeting (`extract_greeting_name`).

**Ask the user which templates to use if they want different ones.** Follow-up templates in the project root follow the pattern `followup-*.md`.

## Script Usage

```bash
# Dry run (default) — preview all eligible follow-ups
python send_followup.py

# Dry run with limit
python send_followup.py --limit 10

# Only follow up contacts whose first email was sent 5+ days ago
python send_followup.py --min-days 5

# Actually send (requires user to say "Please send email")
python send_followup.py --send --min-days 5

# Combine options
python send_followup.py --send --min-days 5 --limit 50

# Use different templates
python send_followup.py --template <followup_template> --original-template <original_template>

# Test mode (writes to crm_test database)
python send_followup.py --test
```

## Workflow

### Step 1: Dry run from the database (always do this first)

```bash
python send_followup.py --min-days 5
```

Review the output — email, name, conference, the `Fwd:` subject, and a preview of the full body (note + forwarded original). All rows come from `contact_status`.

> If the user explicitly asks to refresh first ("the DB might be stale"), run `crm_check.py` once and re-run the dry run. Don't do this by default.

### Step 2: Send with explicit confirmation

Only send if the user says exactly **"Please send email"**.

```bash
python send_followup.py --send --min-days 5
```

Each successful send is written to the `emails` table **immediately** after the Postmark call returns (not batched to the end of the loop) — this closes the same double-send gap documented in `postmark-cold-email` / `email-crm` (fixed in commit `6c64227`). The next follow-up run automatically skips these contacts since their `emails` count is now >1.

### Step 3: (Optional) Verify delivery later

Delivery/open/click/bounce status for the new follow-up rows is filled in by the regular `crm_check.py` runs — no need to run it immediately after sending unless an up-to-the-minute report is requested.

## Important Rules

1. **Never send without explicit permission** — see root `CLAUDE.md`
2. **Always dry run first**
3. **Database is the source of truth** for eligibility — never query Postmark to decide who to follow up with; don't insert a `crm_check.py` step unless explicitly asked
4. **No double follow-ups** — enforced by the email-count check per contact
5. **Use `--min-days` in production** — recommended 3-5 days between initial email and follow-up
6. **All follow-ups are recorded** as new `emails` rows, tracked by the same views `email-crm` uses
7. **Use `--test` with test data** — see root `CLAUDE.md`

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
  send_followup.py renders follow-up note + forwards stored original body
        │
        ▼
  Postmark API  ← used ONLY to send (not to select recipients)
        │
        ▼
  insert_email() writes the new send back to PostgreSQL.emails, immediately
        │
        ▼
  (Out of band)  crm_check.py later fills in delivered_at / opened_at / replies
```
