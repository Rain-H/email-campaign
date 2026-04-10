---
name: weekly-stats
description: Generate weekly email campaign statistics including sent emails, replies, and onboarded users. Use when the user asks about weekly stats, campaign performance, or progress reports.
---

# Weekly Stats Reporter

## Overview

Generate weekly and cumulative statistics for the email campaign, including:
- Emails sent this week / total
- Replies received this week / total
- Users onboarded this week / total
- Conversion funnel metrics

## Usage

```bash
# Show current week stats
python weekly_stats.py

# Show stats for a specific week (ISO week number)
python weekly_stats.py --week 13

# Show stats for last N weeks
python weekly_stats.py --last-weeks 4

# Export to JSON
python weekly_stats.py --export stats.json
```

## Output Format

```
═══════════════════════════════════════════════════════════
  Weekly Stats Report - Week 14 (Mar 31 - Apr 6, 2026)
═══════════════════════════════════════════════════════════

  THIS WEEK                      TOTAL
  ─────────                      ─────
  📤 Sent:      321              📤 Sent:      1,035
  📬 Replies:   7                📬 Replies:   28
  ✅ Interested: 1               ✅ Interested: 7
  🚀 Onboarded: 0                🚀 Onboarded: 1

  CONVERSION FUNNEL
  ─────────────────
  Sent → Reply:     2.7%
  Reply → Interest: 25.0%
  Interest → Onboard: 14.3%

═══════════════════════════════════════════════════════════
```

## Data Sources

- **Sent emails**: `emails` table (`sent_at` timestamp)
- **Replies**: `replies` table (`replied_at` timestamp)
- **Interested**: `replies` table where `is_interested = true`
- **Onboarded**: Contacts with status containing 'onboarded' (or custom criteria)
- **Conversations**: `conversations` table for back-and-forth tracking

## Notes

- Week starts on Monday (ISO week)
- "Onboarded" is defined as a contact who has been added to PaperFox (can be customized)
