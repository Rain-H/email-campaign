#!/usr/bin/env python3
"""
从现有的 crm.json 迁移数据到 PostgreSQL 数据库

Usage:
    python migrate_from_json.py                    # 从 ../crm.json 迁移
    python migrate_from_json.py --source path.json # 指定源文件
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from db_config import get_connection, print_config

DEFAULT_CRM_JSON = Path(__file__).parent.parent / "crm.json"


def parse_timestamp(ts_str):
    """解析时间戳字符串，返回标准格式或None"""
    if not ts_str:
        return None
    try:
        if isinstance(ts_str, str):
            # 尝试 ISO 格式
            try:
                ts_str_clean = ts_str.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts_str_clean)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                # 尝试邮件日期格式 (RFC 2822)
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(ts_str)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
        return None
    except Exception:
        return None


def map_old_status_to_interested(old_status, classification):
    """
    将旧的状态映射到新的 is_interested 布尔值
    返回: True (有兴趣) / False (没兴趣) / None (未回复)
    """
    if classification == "interested":
        return True
    elif classification in ("rejected", "skeptical", "neutral"):
        return False

    if old_status == "interested":
        return True
    elif old_status == "rejected":
        return False

    return None


def migrate_from_json(json_path: Path):
    """从 JSON 文件迁移数据到数据库"""

    if not json_path.exists():
        print(f"❌ 文件不存在: {json_path}")
        sys.exit(1)

    print("=" * 60)
    print("数据迁移工具")
    print("=" * 60)
    print()
    print_config()
    print(f"\n源文件: {json_path}")

    # 读取 JSON
    with open(json_path, "r", encoding="utf-8") as f:
        contacts_data = json.load(f)

    print(f"找到 {len(contacts_data)} 条联系人记录\n")

    # 连接数据库
    try:
        print("正在连接数据库...")
        conn = get_connection()
        cursor = conn.cursor()
        print("✓ 连接成功\n")
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        sys.exit(1)

    migrated_contacts = 0
    migrated_emails = 0
    migrated_replies = 0
    skipped = 0

    print("开始迁移数据...")

    for i, contact_data in enumerate(contacts_data, 1):
        email = contact_data.get("email", "").strip()
        if not email:
            skipped += 1
            continue

        name = contact_data.get("chair_name", "Unknown")
        conference = contact_data.get("conference", "")

        # 1. 插入或更新联系人
        cursor.execute("""
            INSERT INTO contacts (email, name, conference)
            VALUES (%s, %s, %s)
            ON CONFLICT(email) DO UPDATE SET
                name = EXCLUDED.name,
                conference = EXCLUDED.conference
        """, (email, name, conference))
        migrated_contacts += 1

        # 2. 插入邮件记录
        postmark_id = contact_data.get("postmark_message_id", "").strip()
        if postmark_id:
            subject = contact_data.get("subject", "")
            sent_at = parse_timestamp(contact_data.get("sent_at"))
            delivered_at = parse_timestamp(contact_data.get("delivered_at"))
            bounced_at = parse_timestamp(contact_data.get("bounced_at"))
            bounce_type = contact_data.get("bounce_type")
            opened_at = parse_timestamp(contact_data.get("opened_at"))

            # 检查是否已存在
            cursor.execute(
                "SELECT id FROM emails WHERE postmark_message_id = %s",
                (postmark_id,)
            )
            existing = cursor.fetchone()

            if existing:
                # 更新现有记录
                email_id = existing[0]
                cursor.execute("""
                    UPDATE emails SET
                        delivered_at = %s,
                        bounced_at = %s,
                        bounce_type = %s,
                        opened_at = %s
                    WHERE id = %s
                """, (delivered_at, bounced_at, bounce_type, opened_at, email_id))
            else:
                # 插入新记录
                cursor.execute("""
                    INSERT INTO emails (
                        contact_email, postmark_message_id, subject, sent_at,
                        delivered_at, bounced_at, bounce_type, opened_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (email, postmark_id, subject, sent_at, delivered_at,
                      bounced_at, bounce_type, opened_at))
                email_id = cursor.fetchone()[0]
                migrated_emails += 1

            # 3. 插入回复记录
            replied_at = contact_data.get("replied_at")
            if replied_at:
                replied_at_parsed = parse_timestamp(replied_at)
                reply_snippet = contact_data.get("reply_snippet", "")
                old_status = contact_data.get("status", "")
                classification = contact_data.get("reply_classification", "")

                is_interested = map_old_status_to_interested(old_status, classification)

                if is_interested is not None:
                    # 检查是否已有回复记录
                    cursor.execute("SELECT id FROM replies WHERE email_id = %s", (email_id,))
                    existing_reply = cursor.fetchone()

                    if not existing_reply:
                        cursor.execute("""
                            INSERT INTO replies (
                                email_id, replied_at, full_content, is_interested
                            ) VALUES (%s, %s, %s, %s)
                        """, (email_id, replied_at_parsed, reply_snippet, is_interested))
                        migrated_replies += 1

        if i % 10 == 0 or i == len(contacts_data):
            print(f"  进度: {i}/{len(contacts_data)}")

    conn.commit()

    print("\n✅ 迁移完成!")
    print(f"   联系人: {migrated_contacts}")
    print(f"   邮件: {migrated_emails}")
    print(f"   回复: {migrated_replies}")
    if skipped:
        print(f"   跳过: {skipped} (缺少 email 字段)")

    # 显示统计
    print("\n📊 当前状态统计:")
    cursor.execute("SELECT status, count FROM status_summary ORDER BY count DESC")
    for status, count in cursor.fetchall():
        print(f"   {status}: {count}")

    cursor.close()
    conn.close()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="从 crm.json 迁移数据到 PostgreSQL")
    parser.add_argument("--source", type=Path, default=DEFAULT_CRM_JSON,
                        help="源 JSON 文件路径")
    args = parser.parse_args()

    migrate_from_json(args.source)


if __name__ == "__main__":
    main()
