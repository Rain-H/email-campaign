---
name: conference-crawling
description: Crawl academic conference data from EasyChair CFP pages using AI-powered extraction. Extracts conference names, website URLs, chair names, chair affiliations, and chair emails. Uses OpenAI web_search for academic email discovery. Use when the user asks to crawl conferences, find chair affiliations or emails, scrape EasyChair, or build a conference contact list.
---

# Conference Crawling

## Overview

Crawl https://easychair.org/cfp/ to extract conference chair contact info for outreach. Uses Claude API for intelligent data extraction from HTML, Playwright for JS-heavy conference websites, and **OpenAI Responses API (`web_search` tool)** for real-time internet search to find chair emails from academic profiles.

In addition to chair names and emails, capture chair affiliations and use `chair_name + chair_affiliation` to search for official academic profiles where email addresses are listed.

## Crawl Script

Run `crawl_easychair.py` in the project root. The user (or the calling agent) specifies the output file — nothing is hardcoded.

```bash
# Crawl first 100 conferences, output to a specific file
python crawl_easychair.py --limit 100 \
  --input <seed_file.json> \
  --output <output_file.json> \
  --csv-output <output_file.csv>
```

`--input` is an optional seed JSON of `[{"conference_short_name": "..."}, ...]`. If the seed has fewer entries than `--limit`, the crawler fills the rest from the live EasyChair `/cfp/` index — ask the user, or check existing `crawled_easychair_*.json` files, before reusing conferences that were already crawled in a prior batch (avoid wasted API spend on duplicates).

**Ask the user where to save the output if they don't specify.**

## Four-Step Crawl Strategy

### Step 1: EasyChair CFP Page (primary source for chair names)

EasyChair CFP pages often list chairs directly with names and roles. Example: https://easychair.org/cfp/SLVA2026 lists "Prof. Susiji Wickramasinghe (Conference Chair)", track chairs, etc.

For each conference, fetch `https://easychair.org/cfp/{CONF}` and use Claude API to extract:
- Conference full name
- Conference website URL
- Chair names and roles
- Chair affiliations (institution/department)
- Any contact emails on the page

EasyChair pages are plain HTML — no Playwright needed here.

**If we got chair names + affiliations + emails from the CFP page, we're done for this conference.**

### Step 2: Conference Website (for affiliations/emails + additional chairs)

Only needed when Step 1 found chairs without emails, without affiliations, or found no chairs at all:

1. Fetch conference homepage (`requests` first; **Playwright/bot-challenge fallback** for JS-rendered or anti-bot sites — see `fetch_url()`)
2. Scan `<a>` tags for committee-related links: `committee`, `organiz`, `chair`, `people`, `team`, `board`, `contact`
3. Follow real links only (up to 3), never brute-force URLs
4. Send committee page HTML to Claude API — extract chair names, affiliations, and emails
5. Merge with Step 1 data: match chair names from EasyChair with affiliations/emails from conference site

### Step 3: OpenAI Web Search for Chairs (when Steps 1+2 found NO chairs)

When both the CFP page and the conference website yield **zero chair names**, use OpenAI web search to find chairs directly. This is the primary recovery mechanism for conferences with inaccessible websites, missing committee pages, or JS-heavy sites that even Playwright can't render.

Uses `openai_web_search_chairs()` in `crawl_easychair.py`:

- Model: `gpt-4o-mini` for first pass; consider `gpt-4o` for retries (more capable at finding obscure conferences)
- Searches conference website, past editions, IEEE Xplore/ACM DL proceedings, EDAS/EasyChair listings
- Returns up to 5 chairs with name, affiliation, and email (if found)

### Step 4: OpenAI Web Search for Emails (for chairs still missing emails)

For chairs found in Steps 1-3 who have a name (and ideally affiliation) but no email:

**DO NOT** use Google Search, DuckDuckGo, or any traditional search engine scraping. Instead, use **OpenAI Responses API** with the `web_search` tool for real-time internet search (`openai_web_search_email()`).

Search targets: university/institution faculty page, Google Scholar, ORCID, ResearchGate, Semantic Scholar, personal academic site/lab page.

Only keep results with `"confidence": "high"` or `"medium"`. Discard `"low"`.

## Retry Strategy

After an initial crawl, some conferences will still have all-empty chair fields (website down, no committee page, CloudFlare blocking, etc.). Re-run `crawl_easychair.py` with the same output file as `--input` — it re-processes the seed's short names — or build a fresh seed of just the empty-result conferences.

For retries, using `gpt-4o` instead of `gpt-4o-mini` in `openai_web_search_chairs()` significantly improves success rates on hard-to-find conferences (tested: 5/19 recovered vs 1/20 with gpt-4o-mini).

## Email Quality Validation

After finding an email (from any step), a quality validation runs before accepting it (`is_valid_email()`, `validate_email_quality()` in `crawl_easychair.py`). This prevents bad data from entering the dataset.

### Automated checks (code-level)

1. **Bad prefix filter**: Reject emails starting with `noreply@`, `info@`, `admin@`, `webmaster@`, `support@`, `contact@`, `office@`, `secretary@`, `easychair`
2. **Bad domain filter**: Reject emails from obviously fake/placeholder domains: `support.com`, `example.com`, `test.com`, `noreply.com`, `localhost`. Do NOT block free email providers like `gmail.com`, `yahoo.com`, `outlook.com` — many academics use personal email as their professional contact.
3. **Obfuscated email handling**: `name[at]domain[dot]com` / `name (at) domain.com` style addresses are captured as-is, then auto-deobfuscated to standard format.
4. **Domain-affiliation coherence**: If affiliation is known, check whether the email domain plausibly relates to it.

### Claude-powered validation (for borderline cases)

For emails that pass automated checks but have unclear domain match, Claude does a final sanity check on whether the local part / domain plausibly belongs to this person at this affiliation.

## Output Format

**Strict flat JSON/CSV** — one entry per chair, conference info repeated. Conferences with no chair data get one entry with empty chair fields. 7 fields (includes `platform`):

```json
[
  {
    "conference_short_name": "SLVA2026",
    "conference_full_name": "78th Annual Scientific Sessions of the Sri Lanka Veterinary Association",
    "conference_url": "https://example.com/",
    "chair_name": "Susiji Wickramasinghe",
    "chair_affiliation": "University of Peradeniya",
    "chair_email": "scientific_sessions@slva.org",
    "platform": "EasyChair"
  }
]
```

Rules:
- N chairs = N rows (conference info repeated per chair)
- 0 chairs = 1 row with empty `chair_name`, `chair_affiliation`, and `chair_email`
- No extra fields (no role, no source, no error)

## Key Rules

- **Rate limit**: 0.8s between HTTP requests, 0.5s between Claude API calls, 1.0s between OpenAI web search calls
- **No brute-force URLs**: Only follow links actually found on the page
- **No traditional search engine scraping**: Do NOT use Google Search, DuckDuckGo, Bing, or any scraping-based search. Use OpenAI `web_search` tool only.
- **Save progress**: Auto-save after every conference (crawl is resumable/interruptible)
- **Avoid re-crawling**: Before seeding a new batch, diff candidate short names against every existing `crawled_easychair_*.json` to skip conferences already crawled
- **Never send emails to crawled addresses without explicit user permission** — see the `postmark-cold-email` skill for the sending workflow and required confirmation phrase

## Dependencies

```
requests>=2.31.0
beautifulsoup4>=4.12.2
anthropic>=0.18.0
openai>=1.66.0
playwright>=1.40.0
python-dotenv>=1.0.0
```
