#!/usr/bin/env python3
"""
PostgreSQL 数据库配置
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 从项目根目录加载 .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# PostgreSQL 配置
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DATABASE = os.getenv("PG_DATABASE", "crm")
PG_DATABASE_TEST = os.getenv("PG_DATABASE_TEST", "crm_test")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")


def _is_test_mode():
    return os.getenv("USE_TEST_DB", "").strip() in ("1", "true", "yes")


def get_connection(use_test_db=False):
    """返回 PostgreSQL 数据库连接。

    When use_test_db=True or env var USE_TEST_DB=1, connects to the test
    database (PG_DATABASE_TEST) instead of the production database.
    """
    try:
        import psycopg2
    except ImportError:
        raise ImportError(
            "需要安装 psycopg2 库:\n"
            "pip install psycopg2-binary"
        )

    db_name = PG_DATABASE_TEST if (use_test_db or _is_test_mode()) else PG_DATABASE
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=db_name,
        user=PG_USER,
        password=PG_PASSWORD
    )
    return conn


def get_schema_path():
    """返回 schema 文件路径"""
    return Path(__file__).parent / "schema.sql"


def print_config():
    """打印当前数据库配置"""
    db_name = PG_DATABASE_TEST if _is_test_mode() else PG_DATABASE
    label = "TEST" if _is_test_mode() else "PRODUCTION"
    print(f"数据库: PostgreSQL ({label})")
    print(f"  主机: {PG_HOST}")
    print(f"  端口: {PG_PORT}")
    print(f"  数据库: {db_name}")
    print(f"  用户: {PG_USER}")
    if PG_PASSWORD:
        print(f"  密码: {'*' * len(PG_PASSWORD)}")
    else:
        print(f"  密码: (未设置)")
