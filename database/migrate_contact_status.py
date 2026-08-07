#!/usr/bin/env python3
"""Re-apply the contact_status view from schema.sql, with a before/after diff.

The view is CREATE OR REPLACE, so this is idempotent and safe to re-run. Use
it after editing the view definition in schema.sql:

    python3 database/migrate_contact_status.py          # production
    python3 database/migrate_contact_status.py --test   # crm_test

Why this exists: the view's engagement columns are aggregated across every
email sent to a contact. Before 2026-08-07 they came from the newest email
only, so a chair who clicked the first email and merely opened the follow-up
was reported as 'opened_no_reply' and dropped out of the click funnel.
"""

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db_config import get_connection, get_schema_path

VIEW_RE = re.compile(
    r"CREATE OR REPLACE VIEW contact_status AS.*?\n\) r ON true;\n", re.S
)


def extract_view_sql() -> str:
    sql = get_schema_path().read_text()
    m = VIEW_RE.search(sql)
    if not m:
        raise SystemExit(
            "Could not find the contact_status view in schema.sql. If the view "
            "was restructured, update VIEW_RE in this script to match."
        )
    return m.group(0)


def breakdown(cur) -> dict:
    cur.execute("SELECT status, COUNT(*) FROM contact_status GROUP BY status")
    return dict(cur.fetchall())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="use the crm_test database")
    args = ap.parse_args()

    view_sql = extract_view_sql()

    conn = get_connection(use_test_db=args.test)
    cur = conn.cursor()
    cur.execute("SELECT current_database()")
    print(f"connected to: {cur.fetchone()[0]}")

    before = breakdown(cur)
    print("\nBEFORE")
    for k in sorted(before, key=lambda k: -before[k]):
        print(f"  {k:<26}{before[k]}")

    # Replacing the view takes ACCESS EXCLUSIVE on it. Don't queue behind a
    # long reader (a full crm_check run holds the view open for ~an hour) --
    # fail fast and let the operator retry instead.
    cur.execute("SET lock_timeout = '15s'")
    t0 = time.time()
    cur.execute(view_sql)
    conn.commit()
    print(f"\nview replaced OK ({time.time() - t0:.1f}s)")

    t0 = time.time()
    after = breakdown(cur)
    elapsed = time.time() - t0
    print("\nAFTER")
    for k in sorted(after, key=lambda k: -after[k]):
        delta = after[k] - before.get(k, 0)
        print(f"  {k:<26}{after[k]:<8}{delta:+d}")
    print(f"\n  aggregate breakdown query took {elapsed:.1f}s")

    if sum(before.values()) != sum(after.values()):
        print("  WARNING: total contact count changed, that should not happen")

    # The whole point of the change: nobody who clicked any email may still be
    # sitting in a non-clicked bucket.
    cur.execute(
        """
        SELECT COUNT(*) FROM contact_status cs
        WHERE cs.status IN ('opened_no_reply', 'no_reply')
          AND EXISTS (SELECT 1 FROM emails e
                      WHERE e.contact_email = cs.email AND e.clicked_at IS NOT NULL)
        """
    )
    stragglers = cur.fetchone()[0]
    print(f"  clickers still misfiled as opened/no_reply: {stragglers} (expected 0)")

    conn.close()


if __name__ == "__main__":
    main()
