---
name: conference-crawling
description: Crawl academic conference data from EasyChair CFP pages using AI-powered extraction. Extracts conference names, website URLs, chair names, chair affiliations, and chair emails. Uses OpenAI web_search for academic email discovery. Use when the user asks to crawl conferences, find chair affiliations or emails, scrape EasyChair, or build a conference contact list.
---

# Conference Crawling

## Overview

Crawl https://easychair.org/cfp/ to extract conference chair contact info for outreach. Uses Claude API for intelligent data extraction from HTML, Playwright for JS-heavy conference websites, and **OpenAI Responses API (`web_search` tool)** for real-time internet search to find chair emails from academic profiles.

In addition to chair names and emails, capture chair affiliations and use `chair_name + chair_affiliation` to search for official academic profiles where email addresses are listed.

## Crawl Script

Run `crawl_conferences_v2.py` in the project root. The user specifies the output file — nothing is hardcoded.

```bash
# Crawl first 100 conferences, output to user-specified file
python crawl_conferences_v2.py --output <output_file.json>

# Custom limit
python crawl_conferences_v2.py --limit 50 --output <output_file.json>
```

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

1. Fetch conference homepage (`requests` first; **Playwright fallback** if page body < 200 chars — handles JS-rendered sites)
2. Scan `<a>` tags for committee-related links: `committee`, `organiz`, `chair`, `people`, `team`, `board`, `contact`
3. Follow real links only (up to 3), never brute-force URLs
4. Send committee page HTML to Claude API — extract chair names, affiliations, and emails
5. Merge with Step 1 data: match chair names from EasyChair with affiliations/emails from conference site

### Step 3: OpenAI Web Search for Chairs (when Steps 1+2 found NO chairs)

When both the CFP page and the conference website yield **zero chair names**, use OpenAI web search to find chairs directly. This is the primary recovery mechanism for conferences with inaccessible websites, missing committee pages, or JS-heavy sites that even Playwright can't render.

Uses `openai_web_search_chairs()` in `crawl_conferences_v2.py`:

- Model: `gpt-4o-mini` for first pass; **`gpt-4o` for retries** (more capable at finding obscure conferences)
- Searches conference website, past editions, IEEE Xplore/ACM DL proceedings, EDAS/EasyChair listings
- Returns up to 5 chairs with name, affiliation, and email (if found)

### Step 4: OpenAI Web Search for Emails (for chairs still missing emails)

For chairs found in Steps 1-3 who have a name (and ideally affiliation) but no email:

**DO NOT** use Google Search, DuckDuckGo, or any traditional search engine scraping. Instead, use **OpenAI Responses API** with the `web_search` tool for real-time internet search.

#### How it works

1. Initialize OpenAI client using `OPENAI_API_KEY` and optional `OPENAI_BASE_PATH` from `.env`
2. For each chair missing an email, call OpenAI Responses API with `web_search` enabled:
   - Model: `gpt-4o-mini` (cost-effective, supports web_search)
   - Input prompt: structured query asking to find the person's email via academic profile pages
3. OpenAI's model autonomously decides to search the web, parses results, and returns findings
4. Extract the email from the structured response

#### Search targets (specified in the prompt)

The prompt instructs the model to search for the person across these academic sources:
- **University/institution official faculty page** (e.g., `cs.stanford.edu/people/...`)
- **Google Scholar profile** (`scholar.google.com`)
- **ORCID profile** (`orcid.org`)
- **ResearchGate profile** (`researchgate.net`)
- **Semantic Scholar profile** (`semanticscholar.org`)
- **Personal academic website** (personal homepage or lab page)

#### Prompt template

```
Find the academic or professional email address for the following person.

Name: {chair_name}
Affiliation: {affiliation}

Search for this person on:
1. Their university/institution official faculty page
2. Google Scholar profile
3. ORCID profile
4. ResearchGate profile
5. Semantic Scholar profile
6. Personal academic website or lab page

Return ONLY a JSON object:
{
  "chair_email": "the email you found, or empty string if not found",
  "source_url": "the URL where you found this email",
  "confidence": "high / medium / low"
}

Rules:
- Only return an email that clearly belongs to this specific person at this affiliation.
- Prefer institutional emails (e.g., .edu, .ac.uk, .it, university domains) over free email providers.
- Do NOT return generic emails (info@, support@, admin@, noreply@, webmaster@).
- If you cannot find a reliable email, return empty string for chair_email.
- "high" confidence = email found on official faculty page or verified academic profile.
- "medium" confidence = email found on a publication or secondary source.
- "low" confidence = email found but source is uncertain.
```

#### OpenAI API call

```python
response = openai_client.responses.create(
    model="gpt-4o-mini",
    tools=[{"type": "web_search"}],
    input=prompt,
)
result_text = response.output_text
```

Only keep results with `"confidence": "high"` or `"medium"`. Discard `"low"`.

## Retry Strategy

After an initial crawl, some conferences will still have all-empty chair fields (website down, no committee page, CloudFlare blocking, etc.). To retry:

- **EDAS**: `python crawl_edas.py --stage 2 --retry` — built-in, re-processes empty entries
- **EasyChair**: re-run `crawl_conferences_v2.py` — it re-processes conferences in the seed file

For retries, using `gpt-4o` instead of `gpt-4o-mini` in `openai_web_search_chairs()` significantly improves success rates on hard-to-find conferences (tested: 5/19 recovered vs 1/20 with gpt-4o-mini).

## Email Quality Validation

After finding an email (from any step), run a **quality validation** before accepting it. This prevents bad data from entering the dataset.

### Automated checks (code-level)

1. **Bad prefix filter**: Reject emails starting with `noreply@`, `info@`, `admin@`, `webmaster@`, `support@`, `contact@`, `office@`, `secretary@`, `easychair`
2. **Bad domain filter**: Reject emails from obviously fake/placeholder domains:
   - `support.com`, `example.com`, `test.com`, `noreply.com`, `localhost`
   - Note: Do NOT block free email providers like `gmail.com`, `yahoo.com`, `outlook.com` — many academics use personal email as their professional contact
3. **Obfuscated email handling**: Some professors write emails as `name[at]domain[dot]com` or `name (at) domain.com` to prevent spam bots. These should be:
   - Captured as-is from the page
   - Auto-deobfuscated to standard format (e.g., `name[at]domain[dot]com` → `name@domain.com`)
   - Treated as valid emails for storage
4. **Domain-affiliation coherence**: If affiliation is known, check whether the email domain plausibly relates to it. For example:
   - `n.shukla@cineca.it` for Nitin Shukla at CINECA → **GOOD** (domain `cineca.it` matches affiliation `CINECA`)
   - `john@support.com` for John Smith at MIT → **BAD** (domain has no relation to MIT)

### Claude-powered validation (for borderline cases)

For emails that pass automated checks but have medium confidence or unclear domain match, use Claude to do a final sanity check:

```
Evaluate whether this email is likely the correct personal/professional email for this person.

Person: {chair_name}
Affiliation: {affiliation}
Email found: {email}
Source: {source_url}

Consider:
1. Does the email domain relate to the person's known affiliation or institution?
2. Does the local part (before @) plausibly relate to the person's name?
3. Is this a personal professional email, not a shared/generic inbox?

Return JSON: {"valid": true/false, "reason": "brief explanation"}
```

### Examples

| Person | Affiliation | Email Found | Valid? | Reason |
|--------|-------------|-------------|--------|--------|
| Nitin Shukla | CINECA | n.shukla@cineca.it | ✅ Yes | Domain matches affiliation, local part matches name |
| John Smith | MIT | john.smith@mit.edu | ✅ Yes | .edu domain matches university, name matches |
| Jane Doe | University of Tokyo | support@example.com | ❌ No | Generic domain, generic prefix |
| Wei Zhang | Tsinghua University | zhang@tsinghua.edu.cn | ✅ Yes | Domain matches university, name matches |
| Alex Brown | INRIA | contact@inria.fr | ❌ No | Generic prefix "contact@", likely shared inbox |

## Claude API Usage

Send preprocessed HTML (strip `<script>`, `<style>`, `<nav>`, `<footer>`, limit ~4000 chars around relevant section) to Claude with structured extraction prompt. Model: `claude-sonnet-4-20250514`.

Cost estimate: ~100 conferences × ~2-3 calls each × ~$0.01 = ~$2-3 total.

## OpenAI Web Search Usage

Uses OpenAI Responses API with `web_search` tool for Step 3 fallback. Model: `gpt-4o-mini`.

Configuration in `.env`:
```
OPENAI_API_KEY=sk-proj-...
OPENAI_BASE_PATH=https://api.openai.com/v1   # or proxy URL
```

Cost estimate: ~$0.025-0.03 per web search call. For ~100-200 chairs needing search, total ~$3-6.

## Output Format

**Strict flat JSON** — one entry per chair, conference info repeated. Conferences with no chair data get one entry with empty chair fields. Exactly 6 fields:

```json
[
  {
    "conference_short_name": "SLVA2026",
    "conference_full_name": "78th Annual Scientific Sessions of the Sri Lanka Veterinary Association",
    "conference_url": "https://example.com/",
    "chair_name": "Susiji Wickramasinghe",
    "chair_affiliation": "University of Peradeniya",
    "chair_email": "scientific_sessions@slva.org"
  },
  {
    "conference_short_name": "SLVA2026",
    "conference_full_name": "78th Annual Scientific Sessions of the Sri Lanka Veterinary Association",
    "conference_url": "https://example.com/",
    "chair_name": "Thilini Anupama",
    "chair_affiliation": "Sri Lanka Veterinary Association",
    "chair_email": ""
  },
  {
    "conference_short_name": "NOCHAIRS2026",
    "conference_full_name": "Some Conference With No Chairs Found",
    "conference_url": "",
    "chair_name": "",
    "chair_affiliation": "",
    "chair_email": ""
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
- **Save progress**: Auto-save after every conference
- **Skip bad emails**: Filter out noreply, info@, admin@, webmaster, support@, contact@, office@, easychair addresses
- **Domain validation**: Verify email domain plausibly matches chair's affiliation
- **Identity consistency**: Only keep emails that match chair name + affiliation context
- **Discard low-confidence results**: Only accept high/medium confidence emails from OpenAI web search
- **Never send emails to crawled addresses without explicit user permission**

## Dependencies

```
requests>=2.31.0
beautifulsoup4>=4.12.2
anthropic>=0.18.0
openai>=1.66.0
playwright>=1.40.0
python-dotenv>=1.0.0
```
