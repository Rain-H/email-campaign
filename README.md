# Email Campaign

A Python toolkit for academic conference outreach: crawl conference chair contacts from EasyChair and EDAS, send personalized cold emails via Postmark, track delivery/replies in a PostgreSQL CRM, and generate weekly stats.

## Features

- **EasyChair Crawler**: Crawl EasyChair CFP pages for chair names, affiliations, and emails (AI-powered extraction + OpenAI web search)
- **EDAS Crawler**: Login-based EDAS scraper with two-stage design — metadata scrape then chair extraction from external websites
- **Postmark Email Sender**: Send personalized cold emails via Postmark API with template support
- **Follow-up Sender**: Forward-style follow-ups to unreplied contacts
- **CRM Tracking**: Full email lifecycle tracking (sent → delivered → opened → clicked → replied → classified) via Postmark API + IMAP
- **Weekly Stats**: Campaign performance reports with cumulative and per-week breakdowns

## Installation

```bash
pip install -r requirements.txt
playwright install chromium  # needed for JS-heavy conference websites
```

## Quick Start

### 1. Configure Environment

Create a `.env` file:

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

```bash
# EasyChair: crawl CFP listings with AI email enrichment
python crawl_conferences_v2.py --limit 100 --output crawled_conferences_v3.json

# EDAS Stage 1: scrape conference metadata (requires EDAS login)
python crawl_edas.py --stage 1 --output edas_conferences_raw.json

# EDAS Stage 2: extract chairs from external websites
python crawl_edas.py --stage 2 --input edas_conferences_raw.json --output crawled_edas.json

# EDAS: retry conferences that returned empty chair data
python crawl_edas.py --stage 2 --retry
```

### 3. Send Campaign Emails

```bash
# Dry run (always do this first)
python send_postmark.py test_data.csv --template email-template-v3.md --test

# Send (requires explicit confirmation)
python send_postmark.py test_data.csv --template email-template-v3.md --test --send
```

### 4. Send Follow-ups

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
```

### 6. Weekly Stats

```bash
python weekly_stats.py
```

## Project Structure

```
email campaign/
├── crawl_conferences_v2.py     # EasyChair CFP crawler (core library + CLI)
├── crawl_edas.py               # EDAS crawler (Stage 1 + Stage 2 + --retry)
├── send_postmark.py            # Cold email sender via Postmark API
├── send_followup.py            # Follow-up email sender
├── crm_check.py                # CRM status tracker (Postmark + IMAP + AI)
├── weekly_stats.py             # Weekly campaign stats reporter
├── database/                   # PostgreSQL CRM module
│   ├── schema.sql              # Database schema
│   ├── crm_db.py               # Shared DB operations
│   ├── db_config.py            # Connection config
│   └── init_db.py              # Database initializer
├── email-template.md           # Email templates
├── email-template-v2.md
├── email-template-v3.md
├── followup-1.md               # Follow-up template
├── test_data.csv               # Test recipients
├── requirements.txt            # Python dependencies
└── .env                        # Environment variables (not in git)
```

### Data Files (generated)

| File | Source | Description |
|------|--------|-------------|
| `crawled_conferences_v3.json/csv` | EasyChair | Chair contacts from EasyChair CFP crawl |
| `edas_conferences_raw.json` | EDAS | Stage 1 intermediate — conference metadata |
| `crawled_edas.json/csv` | EDAS | Stage 2 output — chair contacts |

## License

MIT
