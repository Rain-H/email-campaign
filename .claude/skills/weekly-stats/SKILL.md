---
name: weekly-stats
description: Generate weekly email campaign statistics including sent emails, replies, interested contacts, and engagement funnel. Use when the user asks about weekly stats, campaign performance, or progress reports.
---

# Weekly Stats Reporter

## Overview

Generate weekly and cumulative statistics for the email campaign via `weekly_stats.py`:
- Emails sent this week / total
- Replies received this week / total, and how many were `interested`
- Outbound/inbound conversation counts this week (from the `conversations` table)
- Cumulative `engaged_contacts`: contacts with 4+ messages in their thread (a proxy for real back-and-forth, not just a reply)

## Usage

```bash
# Show current week stats
python weekly_stats.py

# Show stats for a specific week (ISO week number)
python weekly_stats.py --week 13 --year 2026

# Show stats for last N weeks
python weekly_stats.py --last-weeks 4

# Export to JSON
python weekly_stats.py --export stats.json
```

## Data Sources

All from PostgreSQL, populated by `send_postmark.py` / `send_followup.py` (sends) and `crm_check.py` (replies, classification, conversations sync — see `email-crm`):

- **Sent** — `emails` table, `sent_at` timestamp
- **Replies** — `replies` table, `replied_at` timestamp
- **Interested** — `replies` table where `is_interested = true`
- **Outbound/inbound conversations** — `conversations` table, filtered by `direction`
- **Engaged contacts** — `conversations` grouped by `contact_email` HAVING `COUNT(*) >= 4`

Week boundaries use ISO week numbering, Monday start.

## Note on scope

There is no "onboarded" or PaperFox-signup metric wired up anywhere in this codebase (checked: no `onboard` reference in any `.py`/`.sql` file as of 2026-07-24) — if the user asks for onboarding/conversion-to-signup numbers, that data isn't tracked here and would need a new column/table, not just a new query. Don't report a fabricated "onboarded" number.

## Output Format

```
═══════════════════════════════════════════════════════════
  Weekly Stats Report - Week 14 (Mar 31 - Apr 6, 2026)
═══════════════════════════════════════════════════════════

  THIS WEEK                           TOTAL
  ─────────                           ─────
  Sent:                321            Sent:                1,035
  Replies:             7              Replies:             28
  Interested:          1              Interested:          7
  Outbound convos:     ...            Conversations:       ...
  Inbound convos:      ...            Engaged (4+ msgs):   ...

═══════════════════════════════════════════════════════════
```

(Exact formatting/emoji is whatever `print_stats()` currently renders — read the function if you need the literal layout rather than guessing.)
