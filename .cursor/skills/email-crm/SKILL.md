---
name: email-crm
description: Track email campaign status through full lifecycle via Postmark API, IMAP replies, and Claude AI classification. Use when the user wants to check email status, track delivery, detect replies, classify responses, or generate CRM reports.
---

# Email CRM Status Tracker

## Overview

Tracks every sent cold email through its full lifecycle:
`sent -> delivered/bounced -> clicked -> replied -> AI classified`

All state is stored in PostgreSQL (via `database/crm_db.py`). Optional `--export-json` flag exports to `crm.json`.

## Signal Reliability

Not all tracking signals are equally reliable:

- **Delivered / Bounced** -- Postmark delivery confirmation. Very reliable.
- **Link clicked** -- Postmark TrackLinks rewrites links into tracked redirects. Requires intentional human action, cannot be faked by bots. **Primary engagement signal.**
- **Replied** -- IMAP detection of reply emails. Reliable when matched correctly.
- **Opened (pixel)** -- Postmark tracking pixel. **Unreliable.** False positives from mail scanners (QQ Mail, university gateways auto-fetch images) and false negatives from privacy-blocking clients (Gmail, Apple Mail). Kept as approximate/supplementary signal only.

## Prerequisites

- `POSTMARK_SERVER_TOKEN` in `.env` (for delivery/open/click tracking)
- `EMAIL_ADDRESS` and `EMAIL_PASSWORD` in `.env` (for IMAP reply detection)
- `ANTHROPIC_API_KEY` in `.env` (for reply classification)
- Python packages: `requests`, `python-dotenv`, `anthropic`

## Postmark Server Settings

These must be enabled on the Postmark server (set via API or dashboard):

- `TrackOpens: true` -- injects tracking pixel (supplementary signal only)
- `TrackLinks: HtmlOnly` -- rewrites links for click tracking (primary engagement signal)

**Important:** The HTML body sent to Postmark MUST include `<html><body>...</body></html>` tags, otherwise Postmark cannot inject the tracking pixel.

## Data Model (PostgreSQL)

Three tables: `contacts`, `emails`, `replies`. Status is computed by the `contact_status` view.

See `database/schema.sql` for full schema.

## Status Values (computed by `contact_status` view)

- `replied_interested` -- replied, AI classified as interested
- `replied_not_interested` -- replied, AI classified as not interested
- `clicked_no_reply` -- clicked a link but hasn't replied
- `opened_no_reply` -- opened email but hasn't clicked or replied (unreliable)
- `no_reply` -- delivered but no engagement detected
- `failed` -- bounced/spam

## Postmark APIs

- `GET /messages/outbound/{id}/details` -- delivery/bounce/open/click events per message
- `GET /messages/outbound/opens?recipient={email}` -- open events by recipient (supplementary, unreliable)
- `GET /messages/outbound/clicks?recipient={email}` -- click events by recipient (primary engagement signal)
- `GET /bounces` -- bounced messages

## Reply Detection (IMAP)

Connects to `mail.privateemail.com` via IMAP and searches for replies to campaign emails.

**Matching rules (all must pass):**

1. Check `In-Reply-To` / `References` headers against sent Postmark `Message-ID`s (standard reply detection)
2. Fallback: match by exact campaign subject line (e.g. `Re: A modern alternative to EasyChair for AFC`)
3. Sender email must be in CRM contact list
4. Reply date must be AFTER the campaign `sent_at` timestamp

**Do NOT use broad keyword search** (e.g. "EasyChair", "PaperFox") -- this matches unrelated emails in the inbox and produces false reply detections.

## AI Classification

Claude classifies replies into: `interested` or `rejected` (stored as `is_interested` boolean in DB).

## Usage

`send_postmark.py` writes directly to PostgreSQL on send. `crm_check.py` reads/writes PostgreSQL directly.

```bash
# Send emails (writes to DB automatically)
python3 send_postmark.py --source test --send

# Full sync (Postmark + replies + classify)
python3 crm_check.py

# Check Postmark status only
python3 crm_check.py --postmark-only

# Check replies only
python3 crm_check.py --replies-only

# Show report without syncing
python3 crm_check.py --report

# Export DB to crm.json (optional)
python3 crm_check.py --export-json
```

## Output

Prints a summary table with engagement funnel:

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
  Felix Ramos      felix@cinvestav.mx       BICA 2026    clicked
  ...
```

Note: "Opened" is shown separately as an approximate metric. It is not used as the primary status because tracking pixel data has known false positives (mail scanners) and false negatives (Gmail/Apple Mail blocking).
