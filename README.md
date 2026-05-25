# Email Campaign

A Python toolkit for academic conference outreach: crawl conference chair contacts from EasyChair and EDAS, send personalized cold emails via Postmark, track delivery/replies in a PostgreSQL CRM, and generate weekly stats.

## Features

- **EasyChair Crawler** (`crawl_easychair.py`): Crawl EasyChair CFP pages for chair names, affiliations, and emails (AI-powered extraction + OpenAI web search)
- **EDAS Crawler** (`crawl_edas.py`): Login-based EDAS scraper with two-stage design — metadata scrape then chair extraction from external websites
- **Postmark Email Sender** (`send_postmark.py`): Send personalized cold emails via Postmark API with template support
- **Follow-up Sender** (`send_followup.py`): Forward-style follow-ups to unreplied contacts
- **CRM Tracking** (`crm_check.py`): Full email lifecycle tracking (sent → delivered → opened → clicked → replied → classified) via Postmark API + IMAP
- **Dashboard** (`dashboard.py`): Streamlit campaign performance dashboard
- **Weekly Stats** (`weekly_stats.py`): Campaign performance reports with cumulative and per-week breakdowns

## Installation

```bash
pip install -r requirements.txt
playwright install chromium  # needed for JS-heavy conference websites
```

Initialize the database (first time only):

```bash
python database/init_db.py          # production (crm)
python database/init_db.py --test     # test database (crm_test)
```

## Quick Start

### 1. Configure Environment

Create a `.env` file (see `database/.env.example` for database variables):

```env
# Email sending
POSTMARK_SERVER_TOKEN=your-postmark-token
POSTMARK_SENDER_EMAIL=your-verified-sender@example.com

# IMAP (for reply tracking)
EMAIL_ADDRESS=your-email@example.com
EMAIL_PASSWORD=your-app-password
EMAIL_PROVIDER=privateemail  # or: icloud, gmail, outlook, yahoo

# AI
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# EDAS (optional, for EDAS crawling)
EDAS_USERNAME=your_email@example.com
EDAS_PASSWORD=your_password

# Database
PG_HOST=localhost
PG_PORT=5432
PG_DBNAME=crm
PG_USER=postgres
PG_PASSWORD=your_password
```

### 2. Crawl Conferences

**EasyChair** — enrich chair affiliations and emails from CFP pages and conference websites:

```bash
# Optional seed file: [{"conference_short_name": "nlp4call26"}, ...]
# If the seed has fewer entries than --limit, the crawler fills the rest from the EasyChair index.

python crawl_easychair.py --limit 100 \
  --input seed_easychair_2026-05-14.json \
  --output crawled_easychair_2026-05-14.json \
  --csv-output crawled_easychair_2026-05-14.csv
```

**EDAS** — two-stage crawl (Stage 1 is fast; Stage 2 visits external websites):

```bash
# Stage 1: scrape conference metadata (requires EDAS login)
python crawl_edas.py --stage 1 --output edas_raw.json

# Stage 2: extract chairs from external websites
python crawl_edas.py --stage 2 --input edas_raw.json \
  --output contacts_edas.json --csv-output contacts_edas.csv

# Retry conferences that returned empty chair data
python crawl_edas.py --stage 2 --retry

# Or run both stages in one command
python crawl_edas.py --output contacts_edas.json --csv-output contacts_edas.csv
```

### 3. Send Campaign Emails

Always dry-run first. Use `test_data.csv` with `--test` for safe testing (writes to `crm_test`, not production):

```bash
# Dry run
python send_postmark.py test_data.csv --test

# Send (requires explicit user confirmation: "Please send email")
python send_postmark.py test_data.csv --test --send
```

Default template is `email-template-v5.md`. Override with `--template`.

Recipient files support `.csv`, `.json`, or `.xlsx` with columns: `chair_name`, `chair_email`, `conference_short_name` (and optionally `chair_affiliation`, `platform`).

### 4. Send Follow-ups

Follow-ups forward the original outreach. The original body uses `email-template-v2.md` by default (matching the first campaign format); override with `--original-template`.

```bash
# Preview follow-up candidates
python send_followup.py --test

# Send follow-ups
python send_followup.py --test --send
```

### 5. Check CRM Status

```bash
python crm_check.py          # production
python crm_check.py --test   # test database

# Sync a single contact's full IMAP thread
python sync_one_contact.py someone@university.edu
```

### 6. Dashboard & Weekly Stats

```bash
streamlit run dashboard.py
python weekly_stats.py
python weekly_stats.py --last-weeks 4
```

## Project Structure

```
email campaign/
├── crawl_easychair.py          # EasyChair CFP crawler
├── crawl_edas.py               # EDAS crawler (Stage 1 + Stage 2 + --retry)
├── send_postmark.py            # Cold email sender via Postmark API
├── send_followup.py            # Follow-up email sender
├── crm_check.py                # CRM status tracker (Postmark + IMAP + AI)
├── sync_one_contact.py         # Single-contact IMAP sync utility
├── dashboard.py                # Streamlit campaign dashboard
├── weekly_stats.py             # Weekly campaign stats reporter
├── database/                   # PostgreSQL CRM module
│   ├── schema.sql
│   ├── crm_db.py
│   ├── db_config.py
│   └── init_db.py
├── email-template.md           # Original template (v1)
├── email-template-v2.md        # Outreach template (default for follow-up forwards)
├── email-template-v3.md        # Alternate outreach template
├── email-template-v4.md        # Alternate outreach template
├── email-template-v5.md        # Current cold email template (default for sends)
├── followup-1.md               # Follow-up note template
├── test_data.csv               # Test recipients (local, not in git)
├── requirements.txt
└── .env                        # Environment variables (not in git)
```

### Data Files (generated, gitignored)

Crawl outputs and CRM exports are kept locally but not committed to git. Use dated filenames to track batches.

| File pattern | Source | Description |
|--------------|--------|-------------|
| `seed_easychair_*.json` | Manual / prior crawl | Seed list of `conference_short_name` for EasyChair re-crawl |
| `crawled_easychair_*.json/csv` | EasyChair | Chair contacts from EasyChair CFP crawl |
| `edas_raw.json` | EDAS | Stage 1 intermediate — conference metadata |
| `contacts_edas.json/csv` | EDAS | Stage 2 output — chair contacts |
| `contacts_easychair.csv` | EasyChair | Older EasyChair contact export |
| `followup_*_pending.csv` | CRM export | Follow-up candidate lists for a specific send batch |

## License

MIT
