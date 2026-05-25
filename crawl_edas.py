#!/usr/bin/env python3
"""
EDAS Conference Crawler — Two-stage design.

Stage 1 (fast, requests-only):
  Login to EDAS → scrape conference listing → batch-fetch detail pages → save raw JSON.

Stage 2 (slow, Playwright + AI):
  Read raw JSON → visit external conference websites → extract chairs → search emails.

Usage:
    python crawl_edas.py --stage 1 --output edas_conferences_raw.json --limit 10
    python crawl_edas.py --stage 2 --input edas_conferences_raw.json --output crawled_edas.json --csv-output crawled_edas.csv
    python crawl_edas.py --stage 2 --retry  # re-process conferences with empty chair data
    python crawl_edas.py --output crawled_edas.json --csv-output crawled_edas.csv  # both stages
"""

import argparse
import csv
import json
import os
import signal
import sys
import time
from typing import Dict, List, Optional, Tuple

import requests as http_requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

EDAS_LOGIN_URL = "https://edas.info/login.php"
EDAS_LIST_URL = "https://edas.info/listConferencesSubmit.php"
EDAS_DETAIL_URL = "https://edas.info/showConferenceDetails.php?c={}"

REQUEST_DELAY = 0.5
HTTP_TIMEOUT = 20
PER_CONFERENCE_TIMEOUT = 120

DEFAULT_RAW_OUTPUT = "edas_raw.json"
DEFAULT_OUTPUT = "contacts_edas.json"
DEFAULT_CSV_OUTPUT = "contacts_edas.csv"


# ── Stage 1: EDAS metadata scrape ──────────────────────────────────

def edas_login() -> http_requests.Session:
    """Login to EDAS and return an authenticated session."""
    username = os.getenv("EDAS_USERNAME")
    password = os.getenv("EDAS_PASSWORD")
    if not username or not password:
        print("ERROR: EDAS_USERNAME and EDAS_PASSWORD must be set in .env")
        sys.exit(1)

    session = http_requests.Session()
    r = session.get(EDAS_LOGIN_URL, timeout=HTTP_TIMEOUT)
    soup = BeautifulSoup(r.text, "html.parser")
    login_input = soup.find("input", {"name": "__login"})
    login_token = login_input.get("value", "") if login_input else ""

    data = {
        "__login": login_token,
        "username": username,
        "password": password,
        "logon": "submit",
    }
    session.post(EDAS_LOGIN_URL, data=data, timeout=HTTP_TIMEOUT)
    return session


def scrape_conference_list(session: http_requests.Session) -> List[Dict]:
    """Scrape the EDAS conference listing table. Returns basic metadata per conference."""
    r = session.get(EDAS_LIST_URL, timeout=HTTP_TIMEOUT)
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table", id="sortTable")
    if not table:
        print("ERROR: Could not find conference table (#sortTable). Login may have failed.")
        sys.exit(1)

    conferences = []
    rows = table.find_all("tr")[1:]  # skip header
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 7:
            continue

        # Extract detail page ID from the link
        detail_link = cells[3].find("a", href=True)
        edas_id = ""
        if detail_link:
            href = detail_link.get("href", "")
            if "c=" in href:
                edas_id = href.split("c=")[-1].split("&")[0]

        area = cells[0].get_text(strip=True)
        short_name = cells[1].get_text(strip=True)
        full_name = cells[2].get_text(strip=True)
        where_when = cells[4].get_text(strip=True)
        deadline = cells[5].get_text(strip=True)

        conferences.append({
            "edas_id": edas_id,
            "conference_short_name": short_name,
            "conference_full_name": full_name,
            "conference_url": "",  # filled from detail page
            "area": area,
            "where_when": where_when,
            "deadline": deadline,
        })

    return conferences


def scrape_detail_page(session: http_requests.Session, edas_id: str) -> Dict:
    """Fetch a single EDAS detail page and extract structured fields from the <dl>."""
    url = EDAS_DETAIL_URL.format(edas_id)
    r = session.get(url, timeout=HTTP_TIMEOUT)
    soup = BeautifulSoup(r.text, "html.parser")

    info = {}
    dl = soup.find("dl")
    if dl:
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            key = dt.get_text(strip=True).lower()
            if key == "conference url":
                link = dd.find("a", href=True)
                info["conference_url"] = link["href"] if link else dd.get_text(strip=True)
            elif key == "location":
                info["location"] = dd.get_text(strip=True)
            elif key == "dates":
                info["dates"] = dd.get_text(strip=True)
            elif key == "topic areas":
                info["topic_areas"] = dd.get_text(strip=True)

    return info


def run_stage1(output_path: str, limit: int = 0):
    """Stage 1: Login, scrape listing, fetch detail pages, save raw JSON."""
    print("=" * 60)
    print("  EDAS Crawler — Stage 1: Metadata Scrape")
    print("=" * 60)

    print("\n[1/3] Logging into EDAS...")
    session = edas_login()
    print("  ✓ Login successful")

    print("\n[2/3] Scraping conference listing...")
    conferences = scrape_conference_list(session)
    print(f"  ✓ Found {len(conferences)} conferences")

    if limit > 0:
        conferences = conferences[:limit]
        print(f"  → Limited to {limit} conferences")

    print(f"\n[3/3] Fetching detail pages for {len(conferences)} conferences...")
    for i, conf in enumerate(conferences):
        edas_id = conf.get("edas_id", "")
        if not edas_id:
            continue
        try:
            detail = scrape_detail_page(session, edas_id)
            conf["conference_url"] = detail.get("conference_url", "")
            conf["location"] = detail.get("location", "")
            conf["dates"] = detail.get("dates", "")
            if detail.get("topic_areas"):
                conf["topic_areas"] = detail["topic_areas"]
        except Exception as e:
            print(f"  ! Failed to fetch detail for {conf['conference_short_name']}: {e}")

        if (i + 1) % 20 == 0:
            print(f"  ... {i + 1}/{len(conferences)} done")
        time.sleep(REQUEST_DELAY)

    with open(output_path, "w") as f:
        json.dump(conferences, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Stage 1 complete: {len(conferences)} conferences saved to {output_path}")
    urls_found = sum(1 for c in conferences if c.get("conference_url"))
    print(f"  {urls_found} have external website URLs")
    return conferences


# ── Stage 2: Chair extraction from external websites ───────────────

def _find_empty_short_names(rows: List[Dict]) -> set:
    """Identify conference short names where all rows have empty chair fields."""
    from collections import defaultdict
    by_conf = defaultdict(list)
    for r in rows:
        by_conf[r.get("conference_short_name", "").strip()].append(r)
    empty = set()
    for short, conf_rows in by_conf.items():
        if all(
            not (r.get("chair_name") or "").strip()
            and not (r.get("chair_affiliation") or "").strip()
            and not (r.get("chair_email") or "").strip()
            for r in conf_rows
        ):
            empty.add(short)
    return empty


class CrawlConnectionError(RuntimeError):
    """Fatal connectivity issue while crawling; abort current run immediately."""


def run_stage2(input_path: str, output_path: str, csv_output_path: str,
               limit: int = 0, retry: bool = False):
    """Stage 2: Read raw JSON, visit external websites, extract chairs.

    If retry=True, re-process conferences that have all-empty chair fields.
    """
    mode_label = "Chair Extraction (retry)" if retry else "Chair Extraction"
    print("=" * 60)
    print(f"  EDAS Crawler — Stage 2: {mode_label}")
    print("=" * 60)

    from crawl_easychair import (
        collect_committee_links,
        extract_from_committee_page,
        fetch_url,
        get_claude_client,
        get_openai_client,
        is_connection_error,
        is_valid_email,
        merge_chairs,
        openai_web_search_chairs,
        openai_web_search_email,
        to_output_rows,
        validate_email_quality,
        deobfuscate_email,
    )

    with open(input_path) as f:
        conferences = json.load(f)

    if limit > 0:
        conferences = conferences[:limit]

    # Load existing results for resume support
    existing_rows: List[Dict] = []
    done_short_names: set = set()
    retry_short_names: set = set()
    if os.path.exists(output_path):
        try:
            with open(output_path) as f:
                existing_rows = json.load(f)
            done_short_names = {r["conference_short_name"] for r in existing_rows}
            print(f"  Resuming: {len(done_short_names)} conferences already processed")
        except Exception:
            pass

    if retry and existing_rows:
        retry_short_names = _find_empty_short_names(existing_rows)
        if retry_short_names:
            print(f"  Retry mode: {len(retry_short_names)} conferences with empty chair data")
            existing_rows = [r for r in existing_rows
                            if r.get("conference_short_name", "").strip() not in retry_short_names]
            done_short_names -= retry_short_names
        else:
            print("  Retry mode: no conferences with empty chair data found")

    client = get_claude_client()
    openai_client = get_openai_client()

    all_rows = list(existing_rows)

    def _alarm_handler(signum, frame):
        raise TimeoutError("conference crawl timeout")
    signal.signal(signal.SIGALRM, _alarm_handler)

    to_process = [c for c in conferences if c["conference_short_name"] not in done_short_names]
    print(f"\n  {len(to_process)} conferences to process ({len(done_short_names)} already done)")

    for idx, conf in enumerate(to_process, start=1):
        short = conf["conference_short_name"]
        full = conf["conference_full_name"]
        url = conf.get("conference_url", "")
        print(f"\n[{idx}/{len(to_process)}] {short}: {url or '(no URL)'}")

        chairs = []
        try:
            signal.alarm(PER_CONFERENCE_TIMEOUT)

            # Step 1: Visit conference website, find committee page
            if url:
                try:
                    homepage_html = fetch_url(url, min_length=500)
                    committee_links = collect_committee_links(url, homepage_html)
                    for link in committee_links:
                        try:
                            page_html = fetch_url(link, min_length=500)
                            page_chairs = extract_from_committee_page(client, full or short, page_html)
                            chairs = merge_chairs(chairs, page_chairs)
                        except Exception:
                            continue
                except Exception as e:
                    print(f"  ! Website fetch failed: {e}")
                    if is_connection_error(e):
                        raise CrawlConnectionError(
                            f"Connection error while fetching conference site: {short} ({url})"
                        ) from e

            # Step 2: OpenAI web search fallback if no chairs found
            if not any(c.get("chair_name", "").strip() for c in chairs):
                print(f"  → No chairs from website, trying OpenAI web search...")
                web_chairs = openai_web_search_chairs(openai_client, short, full, url)
                if web_chairs:
                    chairs = web_chairs
                    print(f"  ✓ OpenAI found {len(web_chairs)} chair(s)")
                else:
                    print(f"  ✗ No chairs found")

            # Step 3: OpenAI web search for missing emails
            for c in chairs:
                if c.get("chair_email"):
                    continue
                chair_name = c.get("chair_name", "").strip()
                if not chair_name:
                    continue
                affiliation = c.get("chair_affiliation", "").strip()
                print(f"  → Searching email for: {chair_name} ({affiliation or 'no affiliation'})")
                result = openai_web_search_email(openai_client, chair_name, affiliation)
                if isinstance(result, tuple) and len(result) == 2:
                    email, confidence = result
                else:
                    email, confidence = "", ""
                if email:
                    if validate_email_quality(client, chair_name, affiliation, email):
                        c["chair_email"] = email
                        print(f"  ✓ Found: {email} ({confidence})")
                    else:
                        print(f"  ✗ {email} failed validation")

        except TimeoutError:
            print(f"  ! Timeout, skipping")
        except CrawlConnectionError as e:
            print(f"  ! {e}")
            print("  ! Stopping crawl immediately due to connection error")
            break
        except Exception as e:
            print(f"  ! Error: {e}")
            if is_connection_error(e):
                print("  ! Stopping crawl immediately due to connection error")
                break
        finally:
            signal.alarm(0)

        rows = to_output_rows(short, full, url, chairs)
        # Add platform field
        for r in rows:
            r["platform"] = "EDAS"
        all_rows.extend(rows)

        # Save progress
        _save_output(all_rows, output_path, csv_output_path)
        print(f"  → saved ({len(all_rows)} total rows)")

    print(f"\n✓ Stage 2 complete: {len(all_rows)} rows → {output_path}, {csv_output_path}")


def _save_output(rows: List[Dict], json_path: str, csv_path: str):
    """Save rows to both JSON and CSV."""
    with open(json_path, "w") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    fields = [
        "conference_short_name",
        "conference_full_name",
        "conference_url",
        "chair_name",
        "chair_affiliation",
        "chair_email",
        "platform",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="EDAS Conference Crawler")
    parser.add_argument("--stage", type=int, choices=[1, 2],
                        help="Run only stage 1 or 2 (default: both)")
    parser.add_argument("--input", default=DEFAULT_RAW_OUTPUT,
                        help="Input file for stage 2 (raw JSON from stage 1)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help="Output JSON path (stage 1 raw or stage 2 final)")
    parser.add_argument("--csv-output", default=DEFAULT_CSV_OUTPUT,
                        help="Output CSV path (stage 2)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit number of conferences (0 = all)")
    parser.add_argument("--retry", action="store_true",
                        help="Re-process conferences with empty chair data (stage 2)")
    args = parser.parse_args()

    if args.stage == 1:
        run_stage1(args.output, args.limit)
    elif args.stage == 2:
        run_stage2(args.input, args.output, args.csv_output, args.limit,
                   retry=args.retry)
    else:
        raw_path = args.input
        run_stage1(raw_path, args.limit)
        print()
        run_stage2(raw_path, args.output, args.csv_output, args.limit,
                   retry=args.retry)


if __name__ == "__main__":
    main()
