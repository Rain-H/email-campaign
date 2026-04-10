#!/usr/bin/env python3
"""
Weekly Stats Reporter

Generate weekly and cumulative statistics for the email campaign.

Usage:
    python weekly_stats.py              # Current week stats
    python weekly_stats.py --week 13    # Stats for ISO week 13
    python weekly_stats.py --last-weeks 4  # Last 4 weeks
    python weekly_stats.py --export stats.json  # Export to JSON
"""

import argparse
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from database.db_config import get_connection


def get_week_range(year: int, week: int) -> Tuple[datetime, datetime]:
    """Get start (Monday) and end (Sunday) of ISO week."""
    jan4 = datetime(year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.weekday())
    week_start = start_of_week1 + timedelta(weeks=week - 1)
    week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return week_start, week_end


def get_current_week() -> Tuple[int, int]:
    """Get current ISO year and week number."""
    now = datetime.now()
    return now.isocalendar()[:2]


def get_weekly_stats(conn, year: int, week: int) -> Dict:
    """Get stats for a specific week."""
    week_start, week_end = get_week_range(year, week)
    
    cur = conn.cursor()
    
    # Emails sent this week
    cur.execute("""
        SELECT COUNT(*) FROM emails
        WHERE sent_at >= %s AND sent_at <= %s
    """, (week_start, week_end))
    sent_this_week = cur.fetchone()[0]
    
    # Replies this week
    cur.execute("""
        SELECT COUNT(*) FROM replies
        WHERE replied_at >= %s AND replied_at <= %s
    """, (week_start, week_end))
    replies_this_week = cur.fetchone()[0]
    
    # Interested replies this week
    cur.execute("""
        SELECT COUNT(*) FROM replies
        WHERE replied_at >= %s AND replied_at <= %s
        AND is_interested = true
    """, (week_start, week_end))
    interested_this_week = cur.fetchone()[0]
    
    # Conversations this week (outbound)
    cur.execute("""
        SELECT COUNT(*) FROM conversations
        WHERE direction = 'outbound'
        AND message_at >= %s AND message_at <= %s
    """, (week_start, week_end))
    outbound_this_week = cur.fetchone()[0]
    
    # Conversations this week (inbound)
    cur.execute("""
        SELECT COUNT(*) FROM conversations
        WHERE direction = 'inbound'
        AND message_at >= %s AND message_at <= %s
    """, (week_start, week_end))
    inbound_this_week = cur.fetchone()[0]
    
    cur.close()
    
    return {
        "year": year,
        "week": week,
        "week_start": week_start.strftime("%Y-%m-%d"),
        "week_end": week_end.strftime("%Y-%m-%d"),
        "sent": sent_this_week,
        "replies": replies_this_week,
        "interested": interested_this_week,
        "outbound_conversations": outbound_this_week,
        "inbound_conversations": inbound_this_week,
    }


def get_total_stats(conn) -> Dict:
    """Get cumulative stats."""
    cur = conn.cursor()
    
    # Total contacts
    cur.execute("SELECT COUNT(*) FROM contacts")
    total_contacts = cur.fetchone()[0]
    
    # Total emails sent
    cur.execute("SELECT COUNT(*) FROM emails")
    total_sent = cur.fetchone()[0]
    
    # Total replies
    cur.execute("SELECT COUNT(*) FROM replies")
    total_replies = cur.fetchone()[0]
    
    # Total interested
    cur.execute("SELECT COUNT(*) FROM replies WHERE is_interested = true")
    total_interested = cur.fetchone()[0]
    
    # Total conversations
    cur.execute("SELECT COUNT(*) FROM conversations")
    total_conversations = cur.fetchone()[0]
    
    # Contacts with multiple back-and-forth
    cur.execute("""
        SELECT COUNT(DISTINCT contact_email) FROM conversations
        GROUP BY contact_email
        HAVING COUNT(*) >= 4
    """)
    engaged_contacts = cur.rowcount
    
    cur.close()
    
    return {
        "contacts": total_contacts,
        "sent": total_sent,
        "replies": total_replies,
        "interested": total_interested,
        "conversations": total_conversations,
        "engaged_contacts": engaged_contacts,
    }


def print_stats(weekly: Dict, total: Dict):
    """Print formatted stats report."""
    week_label = f"Week {weekly['week']} ({weekly['week_start']} - {weekly['week_end']})"
    
    print()
    print("═" * 62)
    print(f"  Weekly Stats Report - {week_label}")
    print("═" * 62)
    print()
    print(f"  {'THIS WEEK':<30} {'TOTAL'}")
    print(f"  {'─' * 10:<30} {'─' * 5}")
    print(f"  📤 Sent:      {weekly['sent']:<15} 📤 Sent:      {total['sent']:,}")
    print(f"  📬 Replies:   {weekly['replies']:<15} 📬 Replies:   {total['replies']}")
    print(f"  ✅ Interested: {weekly['interested']:<14} ✅ Interested: {total['interested']}")
    print()
    print(f"  CONVERSATIONS THIS WEEK")
    print(f"  {'─' * 22}")
    print(f"  → Outbound:  {weekly['outbound_conversations']}")
    print(f"  ← Inbound:   {weekly['inbound_conversations']}")
    print()
    
    # Conversion funnel
    reply_rate = (total['replies'] / total['sent'] * 100) if total['sent'] > 0 else 0
    interest_rate = (total['interested'] / total['replies'] * 100) if total['replies'] > 0 else 0
    
    print(f"  CONVERSION FUNNEL (Total)")
    print(f"  {'─' * 22}")
    print(f"  Sent → Reply:     {reply_rate:.1f}%")
    print(f"  Reply → Interest: {interest_rate:.1f}%")
    print()
    print("═" * 62)
    print()


def main():
    parser = argparse.ArgumentParser(description="Weekly Stats Reporter")
    parser.add_argument("--week", type=int, help="ISO week number")
    parser.add_argument("--year", type=int, help="Year (default: current)")
    parser.add_argument("--last-weeks", type=int, help="Show last N weeks")
    parser.add_argument("--export", type=str, help="Export to JSON file")
    args = parser.parse_args()
    
    conn = get_connection()
    
    current_year, current_week = get_current_week()
    year = args.year or current_year
    week = args.week or current_week
    
    if args.last_weeks:
        # Show multiple weeks
        weeks_data = []
        for i in range(args.last_weeks):
            w = week - i
            y = year
            if w <= 0:
                w += 52
                y -= 1
            weekly = get_weekly_stats(conn, y, w)
            weeks_data.append(weekly)
        
        total = get_total_stats(conn)
        
        print()
        print("═" * 62)
        print(f"  Weekly Stats - Last {args.last_weeks} Weeks")
        print("═" * 62)
        print()
        print(f"  {'Week':<12} {'Sent':<10} {'Replies':<10} {'Interested'}")
        print(f"  {'─' * 10:<12} {'─' * 8:<10} {'─' * 8:<10} {'─' * 10}")
        for w in reversed(weeks_data):
            print(f"  Week {w['week']:<6} {w['sent']:<10} {w['replies']:<10} {w['interested']}")
        print()
        print(f"  TOTAL:      {total['sent']:<10} {total['replies']:<10} {total['interested']}")
        print("═" * 62)
        
        if args.export:
            with open(args.export, "w") as f:
                json.dump({"weeks": weeks_data, "total": total}, f, indent=2)
            print(f"Exported to {args.export}")
    else:
        # Single week
        weekly = get_weekly_stats(conn, year, week)
        total = get_total_stats(conn)
        
        print_stats(weekly, total)
        
        if args.export:
            with open(args.export, "w") as f:
                json.dump({"weekly": weekly, "total": total}, f, indent=2)
            print(f"Exported to {args.export}")
    
    conn.close()


if __name__ == "__main__":
    main()
