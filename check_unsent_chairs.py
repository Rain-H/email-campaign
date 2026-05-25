#!/usr/bin/env python3
"""
统计还没发过第一封 cold email 的 chair 数量。

候选池 = 三个 crawl 输出 CSV 合并去重 (按 email):
  - crawled_easychair_2026-05-14.csv          (EasyChair 完整 crawl)
  - crawled_easychair_2026-05-14_sendable.csv (EasyChair 筛掉不可发的子集)
  - contacts_edas_unsent_2026-05-19.csv       (EDAS unsent)

"已发过" = email 在 Neon 生产库 contacts 表里有记录 (等价于 emails 表 >=1 行)
"""
import csv
import sys
from collections import defaultdict
from database.db_config import get_connection


CANDIDATE_FILES = [
    "crawled_easychair_2026-05-14.csv",
    "crawled_easychair_2026-05-14_sendable.csv",
    "contacts_edas_unsent_2026-05-19.csv",
]


def load_candidates():
    """返回 {email_lower: {"name": ..., "conference": ..., "sources": set()}}"""
    pool = {}
    for fname in CANDIDATE_FILES:
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
    print("Loading candidate pool from CSVs ...")
    candidates = load_candidates()
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
    out_file = "unsent_chairs.csv"
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["chair_email", "chair_name", "conference_short_name", "sources"])
        for em, rec in sorted(unsent.items()):
            w.writerow([em, rec["name"], rec["conference"], ";".join(sorted(rec["sources"]))])
    print(f"\n   Full list written to: {out_file}")


if __name__ == "__main__":
    main()
