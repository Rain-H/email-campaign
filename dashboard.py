#!/usr/bin/env python3
"""
Email Campaign Dashboard

Run with: streamlit run dashboard.py
"""

import os

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Bridge Streamlit Cloud secrets into os.environ BEFORE importing db_config,
# because get_connection() reads DATABASE_URL via os.getenv. Streamlit
# Cloud only populates st.secrets, not the process environment. On local
# dev, .env handles it and st.secrets is absent — wrapped in try/except
# so missing secrets.toml doesn't crash local runs.
try:
    for _key in ("DATABASE_URL",):
        if _key in st.secrets and not os.environ.get(_key):
            os.environ[_key] = st.secrets[_key]
except Exception:
    pass

from database.db_config import get_connection


st.set_page_config(
    page_title="Email Campaign Dashboard",
    page_icon="📧",
    layout="wide",
)


# Cold email industry benchmarks (2026 snapshot).
# Sources:
#   - b2bdataindex.com/benchmarks/cold-email-2026/
#   - mailshake.com/blog/cold-email-benchmarks-2026/
#   - prospeo.io/s/cold-email-click-through-rate
# Update once a year.
BENCHMARKS = {
    "open_rate":   {"median": 22.0, "tech": 26.0},
    "click_rate":  {"median": 3.0,  "tech": 3.0},
    "reply_rate":  {"median": 4.0,  "tech": 5.0},
    "bounce_rate": {"target": 2.0},
}


@st.cache_data(ttl=300)
def get_weekly_data(num_weeks: int = 12):
    """获取最近 N 周的数据"""
    conn = get_connection()
    cur = conn.cursor()
    
    weeks = []
    now = datetime.now()
    current_year, current_week, _ = now.isocalendar()
    
    for i in range(num_weeks):
        week = current_week - i
        year = current_year
        if week <= 0:
            week += 52
            year -= 1
        
        # 计算周的起止日期
        jan4 = datetime(year, 1, 4)
        start_of_week1 = jan4 - timedelta(days=jan4.weekday())
        week_start = start_of_week1 + timedelta(weeks=week - 1)
        week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
        
        # 发送数 (按每个 contact 的第几封邮件区分 new vs follow-up)
        # ROW_NUMBER() 给每封邮件按 contact + sent_at 排序，seq=1 是初次邮件，seq>1 是 follow-up
        cur.execute("""
            WITH ranked AS (
                SELECT id, sent_at,
                       ROW_NUMBER() OVER (PARTITION BY contact_email ORDER BY sent_at) AS seq
                FROM emails
            )
            SELECT
                COALESCE(SUM(CASE WHEN seq = 1 THEN 1 ELSE 0 END), 0) AS new_sent,
                COALESCE(SUM(CASE WHEN seq > 1 THEN 1 ELSE 0 END), 0) AS followup_sent
            FROM ranked
            WHERE sent_at >= %s AND sent_at <= %s
        """, (week_start, week_end))
        row = cur.fetchone()
        new_sent = row[0]
        followup_sent = row[1]
        sent = new_sent + followup_sent
        
        # 回复数
        cur.execute("""
            SELECT COUNT(*) FROM replies
            WHERE replied_at >= %s AND replied_at <= %s
        """, (week_start, week_end))
        replies = cur.fetchone()[0]
        
        # 感兴趣数
        cur.execute("""
            SELECT COUNT(*) FROM replies
            WHERE replied_at >= %s AND replied_at <= %s
            AND is_interested = true
        """, (week_start, week_end))
        interested = cur.fetchone()[0]
        
        weeks.append({
            "week": f"W{week}",
            "week_num": week,
            "year": year,
            "week_start": week_start.strftime("%m/%d"),
            "sent": sent,
            "new_sent": new_sent,
            "followup_sent": followup_sent,
            "replies": replies,
            "interested": interested,
        })
    
    cur.close()
    conn.close()
    
    return list(reversed(weeks))


@st.cache_data(ttl=300)
def get_total_stats():
    """获取总计统计"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM contacts")
    total_contacts = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM emails")
    total_sent = cur.fetchone()[0]

    # New vs Follow-up 拆分：每个 contact 的第 1 封邮件 = new，第 2+ 封 = follow-up
    cur.execute("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (PARTITION BY contact_email ORDER BY sent_at) AS seq
            FROM emails
        )
        SELECT
            COALESCE(SUM(CASE WHEN seq = 1 THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN seq > 1 THEN 1 ELSE 0 END), 0)
        FROM ranked
    """)
    row = cur.fetchone()
    total_new_sent = row[0]
    total_followup_sent = row[1]

    cur.execute("SELECT COUNT(*) FROM emails WHERE delivered_at IS NOT NULL")
    total_delivered = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM emails WHERE opened_at IS NOT NULL")
    total_opened = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM emails WHERE clicked_at IS NOT NULL")
    total_clicked = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM emails WHERE bounce_type IS NOT NULL")
    total_bounced = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM replies")
    total_replies = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM replies WHERE is_interested = true")
    total_interested = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM conversations")
    total_conversations = cur.fetchone()[0]

    cur.close()
    conn.close()

    return {
        "contacts": total_contacts,
        "sent": total_sent,
        "new_sent": total_new_sent,
        "followup_sent": total_followup_sent,
        "delivered": total_delivered,
        "opened": total_opened,
        "clicked": total_clicked,
        "bounced": total_bounced,
        "replies": total_replies,
        "interested": total_interested,
        "conversations": total_conversations,
    }


@st.cache_data(ttl=300)
def get_recent_replies(limit: int = 10):
    """获取最近的回复"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT e.contact_email, r.replied_at, r.is_interested, c.name
        FROM replies r
        JOIN emails e ON r.email_id = e.id
        LEFT JOIN contacts c ON e.contact_email = c.email
        ORDER BY r.replied_at DESC
        LIMIT %s
    """, (limit,))
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    return [
        {
            "email": row[0],
            "replied_at": row[1],
            "interested": row[2],
            "name": row[3] or row[0].split("@")[0],
        }
        for row in rows
    ]


@st.cache_data(ttl=300)
def get_platform_stats():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.source_platform, COUNT(*) as sent,
               SUM(CASE WHEN e.opened_at IS NOT NULL THEN 1 ELSE 0 END) as opened
        FROM emails e JOIN contacts c ON c.email = e.contact_email
        GROUP BY c.source_platform ORDER BY sent DESC
    """)
    rows = cur.fetchall()
    sent_data = [{"platform": r[0] or "unknown", "sent": r[1], "opened": r[2]} for r in rows]

    cur.execute("""
        SELECT c.source_platform, r.is_interested, COUNT(*)
        FROM replies r
        JOIN emails e ON e.id = r.email_id
        JOIN contacts c ON c.email = e.contact_email
        GROUP BY c.source_platform, r.is_interested
    """)
    reply_data = cur.fetchall()
    cur.close()
    conn.close()
    return sent_data, reply_data


@st.cache_data(ttl=300)
def get_interested_contacts():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.name, c.email, c.conference, c.source_platform, r.replied_at
        FROM replies r
        JOIN emails e ON e.id = r.email_id
        JOIN contacts c ON c.email = e.contact_email
        WHERE r.is_interested = true
        ORDER BY r.replied_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"name": r[0], "email": r[1], "conference": r[2], "platform": r[3],
             "replied_at": r[4].strftime("%Y-%m-%d") if r[4] else ""} for r in rows]


def main():
    st.title("📧 Email Campaign Dashboard")
    
    # 刷新按钮
    col_refresh, col_spacer = st.columns([1, 5])
    with col_refresh:
        if st.button("🔄 Refresh"):
            st.cache_data.clear()
            st.rerun()
    
    # 总计统计卡片
    st.markdown("---")
    total = get_total_stats()
    
    # 7 列：Sent / Bounced / Open Rate / Click Rate / Replies / Reply Rate / Interested
    col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
    reply_rate = (total['replies'] / total['sent'] * 100) if total['sent'] > 0 else 0
    open_rate = (total['opened'] / total['sent'] * 100) if total['sent'] > 0 else 0
    click_rate = (total['clicked'] / total['sent'] * 100) if total['sent'] > 0 else 0
    bounce_rate = (total['bounced'] / total['sent'] * 100) if total['sent'] > 0 else 0
    interest_share = (total['interested'] / total['replies'] * 100) if total['replies'] > 0 else 0

    bm = BENCHMARKS

    with col1:
        st.metric("📤 Sent", f"{total['sent']:,}")
        st.caption(f"New: {total['new_sent']:,} · Follow-up: {total['followup_sent']:,}")
    with col2:
        st.metric("📭 Bounced", f"{total['bounced']:,}", delta=f"-{bounce_rate:.1f}%", delta_color="inverse")
        st.caption(f"Industry target < {bm['bounce_rate']['target']:.0f}% · You {bounce_rate:.1f}%")
    with col3:
        st.metric("👁 Open Rate", f"{open_rate:.1f}%", f"{total['opened']:,} opened")
        st.caption(
            f"Industry median {bm['open_rate']['median']:.0f}% · "
            f"⚠ inflated by Apple Mail Privacy Protection — see Click Rate"
        )
    with col4:
        st.metric("🖱 Click Rate", f"{click_rate:.1f}%", f"{total['clicked']:,} clicked")
        st.caption(
            f"Industry median {bm['click_rate']['median']:.0f}% · "
            f"You {click_rate - bm['click_rate']['median']:+.1f}pp (real engagement signal)"
        )
    with col5:
        st.metric("📬 Replies", f"{total['replies']:,}")
        st.caption(f"{total['interested']:,} interested of {total['replies']:,}")
    with col6:
        st.metric("📊 Reply Rate", f"{reply_rate:.1f}%")
        st.caption(
            f"Industry median {bm['reply_rate']['median']:.0f}% (Tech {bm['reply_rate']['tech']:.0f}%) · "
            f"You {reply_rate - bm['reply_rate']['median']:+.1f}pp"
        )
    with col7:
        st.metric("✅ Interested", f"{total['interested']:,}")
        st.caption(f"{interest_share:.0f}% of replies")
    
    st.markdown("---")
    
    # 周数据图表
    st.subheader("📈 Weekly Trends")
    
    weeks_to_show = st.slider("Weeks to show", 4, 20, 12)
    weekly_data = get_weekly_data(weeks_to_show)
    df = pd.DataFrame(weekly_data)
    
    # 发送和回复趋势图
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(
            x=df["week"],
            y=df["new_sent"],
            name="New",
            marker_color="#4CAF50",
        ))
        fig1.add_trace(go.Bar(
            x=df["week"],
            y=df["followup_sent"],
            name="Follow-up",
            marker_color="#90A4AE",
        ))
        fig1.update_layout(
            title="Weekly Sent (New vs Follow-up)",
            xaxis_title="Week",
            yaxis_title="Count",
            height=350,
            barmode="group",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig1, use_container_width=True)
    
    with col_chart2:
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=df["week"],
            y=df["replies"],
            name="Replies",
            marker_color="#2196F3"
        ))
        fig2.add_trace(go.Bar(
            x=df["week"],
            y=df["interested"],
            name="Interested",
            marker_color="#FF9800"
        ))
        fig2.update_layout(
            title="Weekly Replies & Interested",
            xaxis_title="Week",
            yaxis_title="Count",
            barmode="group",
            height=350,
        )
        st.plotly_chart(fig2, use_container_width=True)
    
    # 转化漏斗 + 平台分布
    st.markdown("---")
    col_funnel, col_platform = st.columns([1, 1])

    with col_funnel:
        st.subheader("🔄 Conversion Funnel")
        funnel_data = pd.DataFrame({
            "stage": ["Sent", "Opened", "Replied", "Interested"],
            "count": [total["sent"], total["opened"], total["replies"], total["interested"]]
        })
        fig_funnel = go.Figure(go.Funnel(
            y=funnel_data["stage"],
            x=funnel_data["count"],
            textinfo="value+percent initial",
            marker=dict(color=["#4CAF50", "#2196F3", "#FF9800", "#E91E63"])
        ))
        fig_funnel.update_layout(height=320)
        st.plotly_chart(fig_funnel, use_container_width=True)

    with col_platform:
        st.subheader("📡 Platform Breakdown")
        sent_data, reply_data = get_platform_stats()
        df_platform = pd.DataFrame(sent_data)
        fig_p = px.bar(df_platform, x="platform", y=["sent", "opened"],
                       barmode="group", color_discrete_sequence=["#4CAF50", "#2196F3"],
                       labels={"value": "Count", "platform": "Platform", "variable": ""})
        fig_p.update_layout(height=320)
        st.plotly_chart(fig_p, use_container_width=True)

    # Interested 联系人明细
    st.markdown("---")
    st.subheader("✅ Interested Contacts")
    interested_list = get_interested_contacts()
    if interested_list:
        df_int = pd.DataFrame(interested_list)
        df_int.columns = ["Name", "Email", "Conference", "Platform", "Reply Date"]
        st.dataframe(df_int)
    else:
        st.info("No interested replies yet")

    # 最近回复
    st.markdown("---")
    col_recent, col_weekly = st.columns([1, 1])

    with col_recent:
        st.subheader("📋 Recent Replies")
        recent = get_recent_replies(10)
        for r in recent:
            status = "✅" if r["interested"] else "❌"
            date_str = r["replied_at"].strftime("%m/%d") if r["replied_at"] else ""
            st.markdown(f"{status} **{r['name']}** — {date_str}")

    with col_weekly:
        st.subheader("📊 Weekly Breakdown")
        df_display = df[["week", "week_start", "new_sent", "followup_sent", "sent", "replies", "interested"]].copy()
        df_display.columns = ["Week", "Start", "New", "Follow-up", "Sent", "Replies", "Interested"]
        st.dataframe(df_display)


if __name__ == "__main__":
    main()
