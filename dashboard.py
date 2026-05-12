#!/usr/bin/env python3
"""
Email Campaign Dashboard

Run with: streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from database.db_config import get_connection


st.set_page_config(
    page_title="Email Campaign Dashboard",
    page_icon="📧",
    layout="wide",
)


@st.cache(ttl=300, allow_output_mutation=True)
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
        
        # 发送数
        cur.execute("""
            SELECT COUNT(*) FROM emails
            WHERE sent_at >= %s AND sent_at <= %s
        """, (week_start, week_end))
        sent = cur.fetchone()[0]
        
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
            "replies": replies,
            "interested": interested,
        })
    
    cur.close()
    conn.close()
    
    return list(reversed(weeks))


@st.cache(ttl=300, allow_output_mutation=True)
def get_total_stats():
    """获取总计统计"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM contacts")
    total_contacts = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM emails")
    total_sent = cur.fetchone()[0]

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
        "delivered": total_delivered,
        "opened": total_opened,
        "clicked": total_clicked,
        "bounced": total_bounced,
        "replies": total_replies,
        "interested": total_interested,
        "conversations": total_conversations,
    }


@st.cache(ttl=300, allow_output_mutation=True)
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


@st.cache(ttl=300, allow_output_mutation=True)
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


@st.cache(ttl=300, allow_output_mutation=True)
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
            st.caching.clear_cache()
            st.rerun()
    
    # 总计统计卡片
    st.markdown("---")
    total = get_total_stats()
    
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    reply_rate = (total['replies'] / total['sent'] * 100) if total['sent'] > 0 else 0
    open_rate = (total['opened'] / total['sent'] * 100) if total['sent'] > 0 else 0
    bounce_rate = (total['bounced'] / total['sent'] * 100) if total['sent'] > 0 else 0

    with col1:
        st.metric("📤 Sent", f"{total['sent']:,}")
    with col2:
        st.metric("📭 Bounced", f"{total['bounced']:,}", delta=f"-{bounce_rate:.1f}%", delta_color="inverse")
    with col3:
        st.metric("👁 Open Rate", f"{open_rate:.1f}%", f"{total['opened']:,} opened")
    with col4:
        st.metric("📬 Replies", f"{total['replies']:,}")
    with col5:
        st.metric("📊 Reply Rate", f"{reply_rate:.1f}%")
    with col6:
        st.metric("✅ Interested", f"{total['interested']:,}")
    
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
            y=df["sent"],
            name="Sent",
            marker_color="#4CAF50"
        ))
        fig1.update_layout(
            title="Weekly Sent",
            xaxis_title="Week",
            yaxis_title="Count",
            height=350,
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
        df_display = df[["week", "week_start", "sent", "replies", "interested"]].copy()
        df_display.columns = ["Week", "Start Date", "Sent", "Replies", "Interested"]
        st.dataframe(df_display)


if __name__ == "__main__":
    main()
