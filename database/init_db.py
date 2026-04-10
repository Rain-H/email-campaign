#!/usr/bin/env python3
"""
初始化 CRM PostgreSQL 数据库

使用方法：
    python init_db.py          # 初始化生产数据库
    python init_db.py --test   # 初始化测试数据库
"""

import argparse
import os

from db_config import get_connection, get_schema_path, print_config


def init_database():
    """创建数据库并执行 schema"""
    parser = argparse.ArgumentParser(description="Initialize CRM database")
    parser.add_argument("--test", action="store_true",
                        help="Initialize test database (crm_test) instead of production")
    args = parser.parse_args()

    if args.test:
        os.environ["USE_TEST_DB"] = "1"

    print("=" * 60)
    print("初始化 CRM 数据库")
    print("=" * 60)
    print()

    print_config()

    schema_path = get_schema_path()
    print(f"\nSchema 文件: {schema_path}")

    if not schema_path.exists():
        print(f"❌ Schema 文件不存在: {schema_path}")
        return

    # 读取 schema
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    # 执行 schema
    try:
        print("\n正在连接数据库...")
        conn = get_connection()
        conn.autocommit = True
        cursor = conn.cursor()

        print("正在创建表、视图和触发器...")
        cursor.execute(schema_sql)

        cursor.close()
        conn.close()

        print("\n✅ 数据库初始化完成\n")
        print("创建的表:")
        print("  - contacts (联系人)")
        print("  - emails (邮件)")
        print("  - replies (回复)")
        print("\n创建的视图:")
        print("  - contact_status (当前状态)")
        print("  - status_summary (统计摘要)")

    except Exception as e:
        print(f"\n❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    init_database()
