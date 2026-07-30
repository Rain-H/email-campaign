#!/usr/bin/env python3
"""
统计还没发过第一封 cold email 的 chair 数量。

候选池 = 所有匹配的 crawl 输出 CSV 合并去重 (按 email)。默认按文件名 glob
自动发现，而不是硬编码具体日期的文件名——硬编码过一次就必然会在下次重新
crawl 之后过期（不会被自动捡起新文件），需要人工记得去改这份列表。
也可以用 --files 显式传入文件名列表覆盖自动发现。

Crawl 输出统一存放在 data/ 目录下（2026-07-24 起的项目整理）。

"已发过" = email 在 Neon 生产库 contacts 表里有记录 (等价于 emails 表 >=1 行)
"""
import argparse
import csv
import glob
import sys
from collections import defaultdict
from database.db_config import get_connection


# Glob patterns covering both crawlers' output naming conventions.
# All crawl output lives under data/ (see project reorg, 2026-07-24).
CANDIDATE_GLOBS = [
    "data/crawled_easychair_*.csv",
    "data/crawled_edas_*.csv",
    "data/contacts_edas*.csv",
]


def discover_candidate_files():
    """Auto-discover candidate CSVs by glob so newly-crawled files are picked
    up automatically instead of requiring a hardcoded, date-specific list
    that goes stale the moment a new crawl runs."""
    found = []
    seen = set()
    for pattern in CANDIDATE_GLOBS:
        for fname in sorted(glob.glob(pattern)):
            if fname not in seen:
                seen.add(fname)
                found.append(fname)
    return found


def load_candidates(files):
    """返回 {email_lower: {"name": ..., "conference": ..., "sources": set()}}"""
    pool = {}
    for fname in files:
        try:
            with open(fname, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    em = (row.get("chair_email") or "").strip().lower()
                    if not em or "@" not in em:
                        continue
                    rec = pool.setdefault(em, {
                        "name": row.get("chair_name", "").strip(),
                        "conference": row.get("conference_short_name", "").strip(),
                        "sources": set(),
                    })
                    rec["sources"].add(fname)
        except FileNotFoundError:
            print(f"  [warn] missing file: {fname}", file=sys.stderr)
    return pool


def load_sent_emails():
    """返回已发过 cold email 的 email set (小写)"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT LOWER(email) FROM contacts")
    sent = {r[0] for r in cur.fetchall()}
    cur.close()
    conn.close()
    return sent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="+", default=None,
                        help="Explicit list of candidate CSV files "
                             "(default: auto-discover via glob patterns)")
    args = parser.parse_args()

    files = args.files if args.files else discover_candidate_files()
    print(f"Loading candidate pool from {len(files)} CSV file(s): {files}")
    candidates = load_candidates(files)
    print(f"  Unique candidate emails (after dedupe): {len(candidates)}")

    by_source = defaultdict(int)
    for rec in candidates.values():
        for src in rec["sources"]:
            by_source[src] += 1
    for src, n in by_source.items():
        print(f"    - {src}: {n} emails")

    print("\nQuerying Neon production DB for already-sent contacts ...")
    sent = load_sent_emails()
    print(f"  Distinct emails in contacts table: {len(sent)}")

    unsent = {em: rec for em, rec in candidates.items() if em not in sent}
    print(f"\n=> Candidates NOT yet sent first cold email: {len(unsent)}")

    # Break down by source
    unsent_by_source = defaultdict(int)
    for rec in unsent.values():
        for src in rec["sources"]:
            unsent_by_source[src] += 1
    print("\n   Unsent breakdown by source:")
    for src, n in unsent_by_source.items():
        print(f"     - {src}: {n}")

    # Save full unsent list
    out_file = "data/unsent_chairs.csv"
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["chair_email", "chair_name", "conference_short_name", "sources"])
        for em, rec in sorted(unsent.items()):
            w.writerow([em, rec["name"], rec["conference"], ";".join(sorted(rec["sources"]))])
    print(f"\n   Full list written to: {out_file}")


if __name__ == "__main__":
    main()
