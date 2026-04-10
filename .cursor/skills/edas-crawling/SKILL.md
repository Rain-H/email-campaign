---
name: edas-crawling
description: Crawl EDAS conference data with two-stage design. Stage 1 scrapes EDAS metadata (login required). Stage 2 visits external conference websites to extract chair names, affiliations, and emails. Use when the user asks to crawl EDAS, scrape EDAS conferences, or find chairs from EDAS listings.
---

# EDAS Conference Crawling

## Overview

Crawl https://edas.info/ (login required) to extract conference metadata and chair contact info for outreach. Two-stage design separates EDAS scraping from chair extraction.

EDAS detail pages do **not** contain chair information — only conference name, URL, location, dates, and topic areas. Chair data must be extracted from each conference's external website.

## Crawl Script

Run `crawl_edas.py` in the project root.

```bash
# Stage 1 only: scrape EDAS metadata (fast, ~4 min for all conferences)
python crawl_edas.py --stage 1 --output edas_conferences_raw.json

# Stage 1 with limit (for testing)
python crawl_edas.py --stage 1 --output edas_conferences_raw.json --limit 10

# Stage 2 only: extract chairs from external websites (slow, uses AI)
python crawl_edas.py --stage 2 --input edas_conferences_raw.json --output crawled_edas.json --csv-output crawled_edas.csv

# Retry conferences with empty chair data
python crawl_edas.py --stage 2 --retry

# Both stages end-to-end
python crawl_edas.py --output crawled_edas.json --csv-output crawled_edas.csv
```

## Two-Stage Design

### Stage 1: EDAS Metadata Scrape (requests only, ~4 min)

1. Login to EDAS using `EDAS_USERNAME` and `EDAS_PASSWORD` from `.env`
2. GET the conference listing page (`listConferencesSubmit.php`)
3. Parse the `#sortTable` DataTable — extract area, short name, full name, where/when, deadline
4. For each conference, GET its detail page (`showConferenceDetails.php?c={id}`)
5. Extract external conference URL from the `<dl>` structure on the detail page
6. Save all metadata to `edas_conferences_raw.json`

**Output** (`edas_conferences_raw.json`): intermediate file, one entry per conference:

```json
{
  "edas_id": "35165",
  "conference_short_name": "10-scs-2026",
  "conference_full_name": "10th Smart Cities Symposium - 2026",
  "conference_url": "https://www.iet-smartcities-symposium.com/",
  "area": "Engineering",
  "location": "Manama, Bahrain",
  "dates": "December 1-3, 2026",
  "deadline": "Apr 10"
}
```

### Stage 2: Chair Extraction from External Websites

Reads Stage 1 output, visits each conference's external URL. **Reuses the same chair extraction logic as the `conference-crawling` skill** — committee page discovery, Claude extraction, OpenAI web search fallback, and email validation are all imported from `crawl_conferences_v2.py`. See the `conference-crawling` skill for full details on Steps 2+3.

**Resume support**: if interrupted, restart and it skips already-processed conferences.

**Retry support** (`--retry`): re-processes conferences where all chair fields are empty, removing stale empty rows before re-crawling. Uses the same 4-step fallback chain as the initial crawl (see `conference-crawling` skill): requests → Playwright → OpenAI chair search → OpenAI email search. For retries, consider upgrading `openai_web_search_chairs()` to use `gpt-4o` instead of `gpt-4o-mini` for better results on hard-to-find conferences.

## EDAS Login

EDAS login form is at `https://edas.info/login.php`:
- POST with `username`, `password`, `logon=submit`, and `__login` hidden token
- Session cookies maintain authentication

Configuration in `.env`:
```
EDAS_USERNAME=your_email@example.com
EDAS_PASSWORD=your_password
```

## Output Format

Same unified 7-column format as EasyChair crawl, with `platform = "EDAS"`:

```json
[
  {
    "conference_short_name": "10-scs-2026",
    "conference_full_name": "10th Smart Cities Symposium - 2026",
    "conference_url": "https://www.iet-smartcities-symposium.com/",
    "chair_name": "John Smith",
    "chair_affiliation": "University of Bahrain",
    "chair_email": "john.smith@uob.edu.bh",
    "platform": "EDAS"
  }
]
```

## Key Rules

- **Rate limit**: 0.5s between EDAS requests (Stage 1), 0.8s between external website requests (Stage 2)
- **No brute-force URLs**: Only follow links actually found on the page
- **Save progress**: Auto-save after every conference in Stage 2
- **Skip bad emails**: Same validation as EasyChair crawl (see `conference-crawling` skill for full email quality rules)
- **Resume**: Stage 2 skips conferences already in the output file
- **Retry**: `--retry` flag re-processes conferences with all-empty chair fields
- **Never send emails to crawled addresses without explicit user permission**

## Dependencies

All dependencies are listed in `requirements.txt`. EDAS-specific: `EDAS_USERNAME` and `EDAS_PASSWORD` in `.env`.
