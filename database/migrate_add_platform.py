#!/usr/bin/env python3
"""Add source_platform column to contacts table."""

from db_config import get_connection


def migrate(db_name=None):
    conn = get_connection(db_name)
    cur = conn.cursor()
    cur.execute("""
        ALTER TABLE contacts
        ADD COLUMN IF NOT EXISTS source_platform TEXT
    """)
    conn.commit()
    cur.close()
    conn.close()
    print(f"Migration complete: source_platform column added to contacts")


if __name__ == "__main__":
    migrate()
    import os
    os.environ["USE_TEST_DB"] = "1"
    migrate()
    print("Both crm and crm_test migrated.")
