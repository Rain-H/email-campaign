#!/usr/bin/env python3
"""Re-crawl EasyChair conferences with chair affiliation + email enrichment."""

import argparse
import json
import os
import re
import signal
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    from openai import OpenAI as _OpenAI
except ImportError:
    _OpenAI = None

EASYCHAIR_CFP_BASE = "https://easychair.org/cfp/"
DEFAULT_INPUT = "crawled_conferences_v2.json"
DEFAULT_OUTPUT = "crawled_conferences_v2.json"
DEFAULT_LIMIT = 100
REQUEST_DELAY = 0.8
CLAUDE_DELAY = 0.5
HTTP_TIMEOUT = 20
PER_CONFERENCE_TIMEOUT = 120

BAD_EMAIL_PREFIXES = (
    "noreply@",
    "no-reply@",
    "info@",
    "admin@",
    "webmaster@",
    "support@",
    "contact@",
    "office@",
    "secretary@",
    "easychair",
)

BAD_EMAIL_DOMAINS = (
    "support.com",
    "example.com",
    "test.com",
    "noreply.com",
    "localhost",
)

OPENAI_SEARCH_DELAY = 1.0

COMMITTEE_KEYWORDS = ("committee", "organiz", "chair", "people", "team", "board", "contact")


def is_connection_error(err: Exception) -> bool:
    """Detect FATAL connectivity failures (proxy down, OpenAI unreachable).

    Per-site failures like SSL cert errors, DNS failures for one conference
    domain, or connection refused on a single host are NOT fatal — those just
    skip the conference and fall through to OpenAI web search.
    """
    msg = str(err).lower()
    if "openai connection error" in msg:
        return True
    if "cannot connect to proxy" in msg:
        return True
    if "proxyerror" in msg and "127.0.0.1" in msg:
        return True
    return False


def normalize_name(name: str) -> str:
    name = (name or "").strip().lower()
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    name = re.sub(r"\s+", " ", name)
    return name


def deobfuscate_email(email: str) -> str:
    """Try to convert obfuscated email formats back to standard format.

    Handles patterns like:
      name[at]domain[dot]com  →  name@domain.com
      name (at) domain (dot) com  →  name@domain.com
      name{at}domain{dot}com  →  name@domain.com
      name AT domain DOT com  →  name@domain.com
    """
    if not email:
        return email
    result = email.strip()
    # Normalize [at] / (at) / {at} / " at " / " AT " → @
    result = re.sub(r"\s*[\[\(\{]\s*[aA][tT]\s*[\]\)\}]\s*", "@", result)
    result = re.sub(r"\s+[aA][tT]\s+", "@", result)
    # Normalize [dot] / (dot) / {dot} / " dot " / " DOT " → .
    result = re.sub(r"\s*[\[\(\{]\s*[dD][oO][tT]\s*[\]\)\}]\s*", ".", result)
    result = re.sub(r"\s+[dD][oO][tT]\s+", ".", result)
    return result


def is_valid_email(email: str) -> bool:
    if not email:
        return False
    email = deobfuscate_email(email).strip().lower()
    if "@" not in email:
        return False
    if any(email.startswith(p) for p in BAD_EMAIL_PREFIXES):
        return False
    domain = email.split("@", 1)[1]
    if domain in BAD_EMAIL_DOMAINS:
        return False
    return True


def preprocess_html(html: str, max_len: int = 7000) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_len]


def safe_json_from_text(text: str):
    """Extract and parse JSON from text that may contain markdown fences or extra content.

    Handles both JSON objects {...} and arrays [...].
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    # Fallback: extract first JSON object or array
    for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                continue
    return None


_BOT_CHALLENGE_MARKERS = (
    "just a moment",
    "checking your browser",
    "cf-browser-verification",
    "cf-challenge",
    "attention required! | cloudflare",
    "ddos protection by cloudflare",
    "enable javascript and cookies to continue",
    "please enable javascript",
    "_cf_chl_opt",
    "challenges.cloudflare.com",
)


def _looks_like_bot_challenge(html: str) -> bool:
    if not html:
        return False
    snippet = html[:5000].lower()
    return any(marker in snippet for marker in _BOT_CHALLENGE_MARKERS)


def _fetch_via_jina_mirror(url: str) -> str:
    """Fetch page text via r.jina.ai mirror as last-resort fallback."""
    mirror_url = f"https://r.jina.ai/http://{url.lstrip('/')}" if not url.startswith("http") else f"https://r.jina.ai/{url}"
    resp = requests.get(mirror_url, timeout=HTTP_TIMEOUT + 10)
    resp.raise_for_status()
    text = resp.text or ""
    if "error 451" in text.lower() or len(text) < 300:
        raise requests.HTTPError(f"Jina mirror returned unusable content for {url}")
    return text


def fetch_url(url: str, min_length: int = 0) -> str:
    """Fetch a URL with anti-bot fallbacks.

    Order of attempts:
      1. requests.get with Chrome UA
      2. If status is 403/429/503: retry with Safari UA + Referer + Accept-Language
      3. If page is a Cloudflare/JS challenge or shorter than min_length: try headless Chromium
    """
    chrome_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    resp = requests.get(url, headers=chrome_headers, timeout=HTTP_TIMEOUT)

    if resp.status_code in (403, 429, 503):
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}/" if parsed.scheme and parsed.netloc else url
        fallback_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
            "Referer": origin,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        time.sleep(1.0)
        try:
            retry_resp = requests.get(url, headers=fallback_headers, timeout=HTTP_TIMEOUT)
            if retry_resp.status_code < 400:
                resp = retry_resp
        except requests.RequestException:
            pass

    if resp.status_code in (403, 429, 503):
        pw_html = _fetch_with_playwright(url)
        if pw_html and not _looks_like_bot_challenge(pw_html):
            time.sleep(REQUEST_DELAY)
            return pw_html
        # Last-resort fallback for anti-bot blocked pages.
        try:
            print("    ! Trying jina mirror fallback...")
            jina_text = _fetch_via_jina_mirror(url)
            time.sleep(REQUEST_DELAY)
            return jina_text
        except Exception:
            pass
        # Playwright and mirror both failed.
        resp.raise_for_status()

    resp.raise_for_status()
    time.sleep(REQUEST_DELAY)
    html = resp.text

    if _looks_like_bot_challenge(html):
        print(f"    ! Detected bot-challenge page, retrying with Playwright")
        pw_html = _fetch_with_playwright(url)
        if pw_html and not _looks_like_bot_challenge(pw_html):
            return pw_html
        try:
            print("    ! Trying jina mirror fallback...")
            jina_text = _fetch_via_jina_mirror(url)
            return jina_text
        except Exception:
            pass
        raise requests.HTTPError(
            f"403 Bot challenge could not be bypassed: {url}",
            response=resp,
        )

    if min_length > 0 and len(html) < min_length:
        pw_html = _fetch_with_playwright(url)
        if pw_html and len(pw_html) > len(html):
            return pw_html
    return html


def _fetch_with_playwright(url: str) -> Optional[str]:
    """Fetch a URL using headless Chromium for JS-rendered pages."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("    ! Playwright not installed, skipping JS fallback")
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()
            time.sleep(REQUEST_DELAY)
            return html
    except Exception as e:
        print(f"    ! Playwright fetch failed: {e}")
        return None


def get_claude_client():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env")
    if anthropic is None:
        raise RuntimeError("anthropic package missing. Install in your Python environment.")
    return anthropic.Anthropic(api_key=key, timeout=60.0, max_retries=1)


def ask_claude_json(client, prompt: str) -> Dict:
    try:
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1400,
            messages=[{"role": "user", "content": prompt}],
        )
        time.sleep(CLAUDE_DELAY)
        text = msg.content[0].text if msg.content else ""
        data = safe_json_from_text(text)
        return data or {}
    except Exception as e:
        print(f"    ! Claude extraction failed: {e}")
        return {}


def extract_from_cfp(client, conf_short: str, html: str) -> Dict:
    snippet = preprocess_html(html, max_len=9000)
    prompt = f"""
Extract conference chair data from this EasyChair CFP page text.

Conference short name: {conf_short}

Return strict JSON only:
{{
  "conference_full_name": "string",
  "conference_url": "string",
  "chairs": [
    {{
      "chair_name": "string",
      "chair_affiliation": "string",
      "chair_email": "string"
    }}
  ]
}}

Rules:
- Use empty strings when unknown.
- Keep chairs who are conference/track/program chairs.
- Keep chair_affiliation when available (institution/department/school).
- Do not invent emails.
- If an email is obfuscated (e.g. "name[at]domain[dot]com", "name (at) domain.com"), still capture it as-is.

CFP text:
{snippet}
"""
    return ask_claude_json(client, prompt)


def collect_committee_links(home_url: str, html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: List[str] = []
    for a in soup.find_all("a", href=True):
        text = (a.get_text(" ", strip=True) or "").lower()
        href = a["href"].strip()
        merged = f"{text} {href.lower()}"
        if any(k in merged for k in COMMITTEE_KEYWORDS):
            full = urljoin(home_url, href)
            if full.startswith("http"):
                links.append(full)
    seen = set()
    out = []
    for link in links:
        if link not in seen:
            seen.add(link)
            out.append(link)
    if out:
        return out[:3]

    # If no clickable links were found (e.g., mirror markdown / anti-bot),
    # derive a few conservative committee URL candidates from the site root.
    parsed = urlparse(home_url)
    if not parsed.scheme or not parsed.netloc:
        return out[:3]
    base = f"{parsed.scheme}://{parsed.netloc}"
    site_key = parsed.netloc.split(".")[0].lower()
    candidates = [
        f"{base}/index.php/{site_key}-committee/",
        f"{base}/index.php/committee/",
        f"{base}/committee/",
        f"{base}/committees/",
        f"{base}/organizing-committee/",
    ]
    for cand in candidates:
        if cand not in seen:
            seen.add(cand)
            out.append(cand)
    return out[:3]


def _regex_extract_chairs_from_text(text: str, max_chairs: int = 8) -> List[Dict]:
    """Fallback extractor for markdown/plain-text committee pages when Claude returns empty."""
    if not text:
        return []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    role_tokens = (
        "general chair",
        "conference chair",
        "program chair",
        "tpc chair",
        "technical program chair",
        "organizing chair",
        "steering committee",
    )
    name_pat = re.compile(
        r"(?:\bProf\.|\bDr\.|\bAssoc\. Prof\.|\bAsst\. Prof\.)\s*\[?([A-Z][A-Za-z\-\s'.]{2,80})\]?"
    )
    chairs: List[Dict] = []
    seen = set()
    for i, line in enumerate(lines):
        low = line.lower()
        if not any(tok in low for tok in role_tokens):
            continue
        window = " ".join(lines[i : i + 3])
        for m in name_pat.finditer(window):
            name = (m.group(1) or "").strip(" ,.;:")
            if not name:
                continue
            key = normalize_name(name)
            if key in seen:
                continue
            seen.add(key)
            chairs.append(
                {
                    "chair_name": name,
                    "chair_affiliation": "",
                    "chair_email": "",
                }
            )
            if len(chairs) >= max_chairs:
                return chairs
    return chairs


def extract_from_committee_page(client, conference_name: str, html: str) -> List[Dict]:
    snippet = preprocess_html(html, max_len=7000)
    prompt = f"""
Extract conference chairs from this committee/contact page text.

Conference: {conference_name}

Return strict JSON only:
{{
  "chairs": [
    {{
      "chair_name": "string",
      "chair_affiliation": "string",
      "chair_email": "string"
    }}
  ]
}}

Rules:
- Include conference chairs, program chairs, track chairs, general chairs, steering committee chairs, and organizing committee chairs.
- Also include committee members who have a named leadership role (e.g. "Dean", "Director", "Chairman", "Coordinator").
- If the page only lists committee members without explicit "chair" titles, include the first 5 listed members.
- Use empty strings for missing fields.
- Do not invent emails.
- If an email is obfuscated (e.g. "name[at]domain[dot]com", "name (at) domain.com"), still capture it as-is.

Page text:
{snippet}
"""
    data = ask_claude_json(client, prompt)
    chairs = data.get("chairs", []) if isinstance(data, dict) else []
    if any((c.get("chair_name", "") or "").strip() for c in chairs):
        return chairs
    # Claude occasionally returns empty on markdown-heavy committee pages.
    regex_chairs = _regex_extract_chairs_from_text(snippet)
    if regex_chairs:
        print(f"    ! Regex fallback extracted {len(regex_chairs)} chair(s)")
        return regex_chairs
    return chairs


def get_openai_client():
    """Initialize OpenAI client for web search, using local HTTP proxy if set."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set in .env")
    if _OpenAI is None:
        raise RuntimeError("openai package missing. pip install openai>=1.66.0")
    base_url = os.getenv("OPENAI_BASE_PATH", "https://api.openai.com/v1")
    proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    kwargs = dict(api_key=key, base_url=base_url, timeout=60.0, max_retries=1)
    if proxy:
        import httpx
        kwargs["http_client"] = httpx.Client(proxy=proxy)
        print(f"OpenAI client using proxy: {proxy}")
    return _OpenAI(**kwargs)


def openai_web_search_email(openai_client, chair_name: str, affiliation: str) -> Tuple[str, str]:
    """Use OpenAI Responses API with web_search to find a chair's email.

    Returns (email, confidence) tuple. confidence is 'high', 'medium', 'low', or ''.
    """
    prompt = f"""Find the academic or professional email address for the following person.

Name: {chair_name}
Affiliation: {affiliation}

Search for this person on:
1. Their university/institution official faculty page
2. Google Scholar profile
3. ORCID profile
4. ResearchGate profile
5. Semantic Scholar profile
6. Personal academic website or lab page

Return ONLY a JSON object, no other text:
{{
  "chair_email": "the email you found, or empty string if not found",
  "source_url": "the URL where you found this email",
  "confidence": "high / medium / low"
}}

Rules:
- Only return an email that clearly belongs to this specific person at this affiliation.
- Prefer institutional emails (e.g., .edu, .ac.uk, .it, university domains) over free email providers, but free providers (gmail etc.) are acceptable if that's what they use.
- Do NOT return generic emails (info@, support@, admin@, noreply@, webmaster@, contact@, office@).
- If an email is obfuscated (e.g. "name[at]domain[dot]com"), convert it to standard format (name@domain.com).
- If you cannot find a reliable email, return empty string for chair_email.
- "high" confidence = email found on official faculty page or verified academic profile.
- "medium" confidence = email found on a publication or secondary source.
- "low" confidence = email found but source is uncertain.
"""
    try:
        response = openai_client.responses.create(
            model="gpt-4o-mini",
            tools=[{"type": "web_search"}],
            input=prompt,
        )
        time.sleep(OPENAI_SEARCH_DELAY)
        result_text = response.output_text or ""
        data = safe_json_from_text(result_text)
        if not isinstance(data, dict):
            return ("", "")
        email = (data.get("chair_email", "") or "").strip()
        confidence = (data.get("confidence", "") or "").strip().lower()
        if not is_valid_email(email):
            return ("", "")
        # Only accept high or medium confidence
        if confidence not in ("high", "medium"):
            print(f"    ! OpenAI search found {email} but confidence is '{confidence}', discarding")
            return ("", "")
        return (email, confidence)
    except Exception as e:
        print(f"    ! OpenAI web search failed: {e}")
        if is_connection_error(e):
            raise RuntimeError(f"OpenAI connection error: {e}") from e
        return ("", "")


def openai_web_search_chairs(openai_client, conf_short: str, conf_full: str, conf_url: str) -> List[Dict]:
    """Use OpenAI web search to find conference chairs when Steps 1+2 found nothing.

    Returns a list of chair dicts with chair_name, chair_affiliation, chair_email.
    """
    conf_label = conf_full or conf_short
    url_hint = f"\nConference website: {conf_url}" if conf_url else ""

    prompt = f"""Find the organizing committee chairs for this academic conference.

Conference: {conf_label} ({conf_short}){url_hint}

Search the conference website, EasyChair page, and any related pages to find the conference chairs / organizers.

Return ONLY a JSON array of chair objects, no other text:
[
  {{
    "chair_name": "Full Name",
    "chair_affiliation": "University or Organization",
    "chair_email": "email if found, or empty string"
  }}
]

Rules:
- Return general chairs, program chairs, and organizing chairs.
- Do NOT return track chairs, session chairs, or regular committee members.
- Include affiliation if you can find it.
- Include email if you can find it on their faculty page or academic profile.
- Do NOT return generic emails (info@, support@, admin@, noreply@, contact@, office@).
- If you cannot find any chairs at all, return an empty array [].
- Maximum 5 chairs.
"""
    try:
        response = openai_client.responses.create(
            model="gpt-4o-mini",
            tools=[{"type": "web_search"}],
            input=prompt,
        )
        time.sleep(OPENAI_SEARCH_DELAY)
        result_text = response.output_text or ""
        data = safe_json_from_text(result_text)
        if not isinstance(data, list):
            return []
        chairs = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = (item.get("chair_name", "") or "").strip()
            if not name:
                continue
            email = (item.get("chair_email", "") or "").strip()
            if email and not is_valid_email(email):
                email = ""
            chairs.append({
                "chair_name": name,
                "chair_affiliation": (item.get("chair_affiliation", "") or "").strip(),
                "chair_email": email,
            })
        return chairs
    except Exception as e:
        print(f"    ! OpenAI chair search failed: {e}")
        if is_connection_error(e):
            raise RuntimeError(f"OpenAI connection error: {e}") from e
        return []


def _name_matches_local_part(chair_name: str, local_part: str) -> bool:
    """Check if the email local part plausibly contains parts of the person's name."""
    name_parts = normalize_name(chair_name).split()
    # Remove titles
    titles = {"prof", "dr", "professor", "mr", "mrs", "ms"}
    name_parts = [p for p in name_parts if p not in titles and len(p) >= 2]
    if not name_parts:
        return False
    local_lower = local_part.lower().replace(".", " ").replace("_", " ").replace("-", " ")
    # If at least 2 name parts appear in local, or last name appears, it's a match
    matches = sum(1 for p in name_parts if p in local_lower)
    return matches >= 2 or (len(name_parts) >= 1 and name_parts[-1] in local_lower)


def validate_email_quality(claude_client, chair_name: str, affiliation: str, email: str) -> bool:
    """Use Claude to validate whether a found email is plausibly correct.

    Performs automated domain checks first, then uses Claude for borderline cases.
    """
    if not email or not is_valid_email(email):
        return False

    email_lower = email.strip().lower()
    local_part, domain = email_lower.split("@", 1)

    # Quick reject: domain is a known bad domain
    if domain in BAD_EMAIL_DOMAINS:
        return False

    # Quick accept: local part clearly matches person's name (works for any domain incl. gmail/yahoo)
    if _name_matches_local_part(chair_name, local_part):
        return True

    # Quick accept: domain clearly matches affiliation
    affil_lower = (affiliation or "").lower()
    domain_parts = domain.replace(".", " ").split()
    affil_words = re.sub(r"[^a-z0-9\s]", " ", affil_lower).split()
    domain_match = any(
        dp in affil_lower for dp in domain_parts if len(dp) >= 3
    )
    affil_match = any(
        aw in domain for aw in affil_words if len(aw) >= 4
    )
    if domain_match or affil_match:
        return True

    # For unclear cases, ask Claude to evaluate
    prompt = f"""Evaluate whether this email is likely the correct personal/professional email for this person.

Person: {chair_name}
Affiliation: {affiliation}
Email found: {email}

Consider:
1. Does the email domain relate to the person's known affiliation or institution?
2. Does the local part (before @) plausibly relate to the person's name?
3. Is this a personal professional email, not a shared/generic inbox?
4. Free email providers (gmail, yahoo, outlook) are acceptable if the local part matches the person's name.

Return JSON only: {{"valid": true or false, "reason": "brief explanation"}}
"""
    data = ask_claude_json(claude_client, prompt)
    if isinstance(data, dict):
        return bool(data.get("valid", False))
    return False


def merge_chairs(base: List[Dict], additions: List[Dict]) -> List[Dict]:
    merged = [dict(x) for x in base]
    by_name = {normalize_name(c.get("chair_name", "")): c for c in merged if c.get("chair_name")}
    for a in additions:
        name_key = normalize_name(a.get("chair_name", ""))
        if not name_key:
            continue
        if name_key in by_name:
            target = by_name[name_key]
            if not target.get("chair_affiliation") and a.get("chair_affiliation"):
                target["chair_affiliation"] = a.get("chair_affiliation", "")
            if not target.get("chair_email") and is_valid_email(a.get("chair_email", "")):
                target["chair_email"] = a.get("chair_email", "")
        else:
            new_item = {
                "chair_name": a.get("chair_name", "").strip(),
                "chair_affiliation": a.get("chair_affiliation", "").strip(),
                "chair_email": a.get("chair_email", "").strip() if is_valid_email(a.get("chair_email", "")) else "",
            }
            merged.append(new_item)
            by_name[name_key] = new_item
    return merged


def chairs_need_more(chairs: List[Dict]) -> bool:
    if not chairs:
        return True
    for c in chairs:
        if not c.get("chair_email") or not c.get("chair_affiliation"):
            return True
    return False


def to_output_rows(conf_short: str, conf_full: str, conf_url: str, chairs: List[Dict],
                   platform: str = "EasyChair") -> List[Dict]:
    if not chairs:
        return [{
            "conference_short_name": conf_short,
            "conference_full_name": conf_full or "",
            "conference_url": conf_url or "",
            "chair_name": "",
            "chair_affiliation": "",
            "chair_email": "",
            "platform": platform,
        }]

    rows = []
    for c in chairs:
        raw_email = (c.get("chair_email", "") or "").strip()
        email = deobfuscate_email(raw_email) if is_valid_email(raw_email) else ""
        rows.append({
            "conference_short_name": conf_short,
            "conference_full_name": conf_full or "",
            "conference_url": conf_url or "",
            "chair_name": (c.get("chair_name", "") or "").strip(),
            "chair_affiliation": (c.get("chair_affiliation", "") or "").strip(),
            "chair_email": email,
            "platform": platform,
        })
    return rows


def load_seed_short_names(input_path: str, limit: int) -> List[str]:
    out: List[str] = []
    seen = set()
    if os.path.exists(input_path):
        with open(input_path, "r") as f:
            data = json.load(f)
        for row in data:
            short = (row.get("conference_short_name") or "").strip()
            if short and short not in seen:
                seen.add(short)
                out.append(short)
            if len(out) >= limit:
                break

    # Fallback: input file may be partial/overwritten. Rebuild list from EasyChair index.
    if len(out) < limit:
        need = limit - len(out)
        print(f"Seed file has only {len(out)} unique conferences, fetching {need} more from EasyChair index...")
        try:
            index_html = fetch_url(EASYCHAIR_CFP_BASE)
            soup = BeautifulSoup(index_html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = (a.get("href") or "").strip()
                if not href.startswith("/cfp/"):
                    continue
                short = href.split("/cfp/", 1)[1].strip().strip("/")
                if not short or short.lower() in ("", "index"):
                    continue
                if short not in seen:
                    seen.add(short)
                    out.append(short)
                if len(out) >= limit:
                    break
        except Exception as e:
            print(f"Warning: could not fetch EasyChair index fallback: {e}")
    return out


def save_json(path: str, data: List[Dict]):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_csv(path: str, rows: List[Dict]):
    import csv
    fields = [
        "conference_short_name",
        "conference_full_name",
        "conference_url",
        "chair_name",
        "chair_affiliation",
        "chair_email",
        "platform",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def crawl_one_conference(client, openai_client, conf_short: str) -> List[Dict]:
    cfp_url = f"{EASYCHAIR_CFP_BASE}{conf_short}"
    print(f"  - {conf_short}: {cfp_url}")

    conf_full = ""
    conf_url = ""
    chairs = []

    # Step 1: EasyChair CFP page
    try:
        cfp_html = fetch_url(cfp_url)
        cfp_data = extract_from_cfp(client, conf_short, cfp_html)
        conf_full = (cfp_data.get("conference_full_name", "") if isinstance(cfp_data, dict) else "").strip()
        conf_url = (cfp_data.get("conference_url", "") if isinstance(cfp_data, dict) else "").strip()
        if isinstance(cfp_data, dict):
            for c in cfp_data.get("chairs", []) or []:
                chairs.append({
                    "chair_name": (c.get("chair_name", "") or "").strip(),
                    "chair_affiliation": (c.get("chair_affiliation", "") or "").strip(),
                    "chair_email": (c.get("chair_email", "") or "").strip() if is_valid_email(c.get("chair_email", "")) else "",
                })
    except Exception as e:
        print(f"    ! CFP fetch failed: {e}")

    # Step 2: conference website fallback
    if chairs_need_more(chairs) and conf_url:
        try:
            homepage_html = fetch_url(conf_url)
            committee_links = collect_committee_links(conf_url, homepage_html)
            website_chairs = []
            for link in committee_links:
                try:
                    page_html = fetch_url(link)
                    website_chairs.extend(extract_from_committee_page(client, conf_full or conf_short, page_html))
                except Exception:
                    continue
            chairs = merge_chairs(chairs, website_chairs)
        except Exception:
            pass

    # Step 3: OpenAI web search for chairs (when Steps 1+2 found nothing)
    if not any(c.get("chair_name", "").strip() for c in chairs):
        print(f"    -> No chairs found via EasyChair/website, trying OpenAI web search...")
        web_chairs = openai_web_search_chairs(openai_client, conf_short, conf_full, conf_url)
        if web_chairs:
            chairs = web_chairs
            print(f"    ✓ OpenAI found {len(web_chairs)} chair(s)")
        else:
            print(f"    ✗ OpenAI found no chairs either")

    # Step 4: OpenAI web search for missing emails
    for c in chairs:
        if c.get("chair_email"):
            continue
        chair_name = c.get("chair_name", "").strip()
        if not chair_name:
            continue
        affiliation = c.get("chair_affiliation", "").strip()
        print(f"    -> OpenAI web search for: {chair_name} ({affiliation or 'no affiliation'})")
        email, confidence = openai_web_search_email(openai_client, chair_name, affiliation)
        if email:
            # Validate email quality
            if validate_email_quality(client, chair_name, affiliation, email):
                c["chair_email"] = email
                print(f"    ✓ Found & validated: {email} (confidence: {confidence})")
            else:
                print(f"    ✗ Found {email} but failed quality validation, discarding")

    return to_output_rows(conf_short, conf_full, conf_url, chairs)


def main():
    parser = argparse.ArgumentParser(description="Crawl conference chairs with affiliation + email enrichment")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Number of conferences to crawl")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Seed json to get conference short names")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output JSON path")
    parser.add_argument("--csv-output", default="crawled_conferences_v2.csv", help="Output CSV path")
    args = parser.parse_args()

    client = get_claude_client()
    openai_client = get_openai_client()
    short_names = load_seed_short_names(args.input, args.limit)
    if not short_names:
        raise RuntimeError("No conference short names found in input file.")

    print(f"Will crawl {len(short_names)} conferences")
    all_rows: List[Dict] = []
    def _alarm_handler(signum, frame):
        raise TimeoutError("conference crawl timeout")

    signal.signal(signal.SIGALRM, _alarm_handler)

    for idx, conf_short in enumerate(short_names, start=1):
        print(f"[{idx}/{len(short_names)}] crawling {conf_short}")
        rows = []
        try:
            signal.alarm(PER_CONFERENCE_TIMEOUT)
            rows = crawl_one_conference(client, openai_client, conf_short)
        except TimeoutError:
            print(f"    ! Timeout on {conf_short}, skipping")
            rows = to_output_rows(conf_short, "", "", [])
        except Exception as e:
            print(f"    ! Unexpected error on {conf_short}: {e}")
            rows = to_output_rows(conf_short, "", "", [])
        finally:
            signal.alarm(0)
        all_rows.extend(rows)
        save_json(args.output, all_rows)
        save_csv(args.csv_output, all_rows)
        print(f"    saved progress: {len(all_rows)} rows")

    print(f"Done. JSON: {args.output} | CSV: {args.csv_output}")


if __name__ == "__main__":
    main()
