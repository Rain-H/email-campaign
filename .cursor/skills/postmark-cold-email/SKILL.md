---
name: postmark-cold-email
description: Send personalized cold emails via Postmark API using conference data. Use when the user wants to send outreach emails, cold emails, campaign emails, or asks about Postmark email sending.
---

# Postmark Cold Email Sender

## Overview

Send personalized cold outreach emails to conference chairs using Postmark's transactional email API. The user provides the data file and template at invocation time — nothing is hardcoded.

## Prerequisites

- **Postmark API key**: Set `POSTMARK_SERVER_TOKEN` in `.env`
- **Sender email**: Set `POSTMARK_SENDER_EMAIL` in `.env` (must be a verified sender/domain in Postmark)
- **Python packages**: `requests`, `python-dotenv`, `psycopg2`

## Data Source

The user specifies the recipient data file when invoking the skill. Supported formats:

| Format | Required columns |
|---|---|
| `.csv` | `conference_short_name`, `chair_name`, `chair_email` |
| `.json` | Same fields as CSV, as a list of objects |
| `.xlsx` | Name (col A), email (col B), Conference short name (col H) |

Only rows with a non-empty `chair_email` are eligible for sending. Generic emails (noreply@, admin@, etc.) are automatically filtered out.

**Ask the user which data file to use if they don't specify one.**

## Email Template

The user specifies the template file via `--template`. Template format: first line is `Subject: ...`, rest is the body.

Placeholders:

| Placeholder | Source field |
|---|---|
| `[Conference Name]` | `conference_short_name` |
| `[Name]` | Smart greeting: "Prof./Dr. LastName" if title present, otherwise first name, fallback "there" |

**Ask the user which template to use if they don't specify one.** Available templates in the project root have the pattern `email-template*.md`.

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

```
- [ ] Ask user for data file and template (if not specified)
- [ ] Run dry run: python send_postmark.py <data_file> --template <template>
- [ ] Show preview: count, sample subjects, sample bodies
- [ ] Wait for user to say "Please send email"
```

### Step 2: Send with confirmation

After user says exactly **"Please send email"**:

1. Run with `--send` flag
2. Emails sent one by one with 0.5s delay
3. Print summary: sent count, failed count

### Step 3: Results logged to PostgreSQL

Send results are written directly to PostgreSQL via `database/crm_db.py` (contacts + emails tables).

## Important Rules

1. **Never send without user confirmation** — always do a dry run first. User must say exactly "Please send email"
2. **Ask for file paths** — never assume which data file or template to use; ask the user
3. **Use `--test` with test data** — when using `test_data.csv`, always add `--test` so results go to `crm_test`
4. **Deduplicate** — same email address should only receive one email
5. **Skip bad emails** — noreply@, admin@, webmaster@, info@, helpdesk@, registrar@, support@, easychair
6. **Log everything** — send results are saved directly to PostgreSQL database

## Error Handling

| Postmark Error Code | Meaning | Action |
|---|---|---|
| 0 | Success | Log as sent |
| 300 | Invalid email | Skip, log as invalid |
| 406 | Inactive recipient | Skip, log as bounced |
| 429 | Rate limit | Wait 1s, retry once |
| Other | API error | Log error, continue |
