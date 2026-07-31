import { sql } from "./db";
import { getWeekRanges } from "./weeks";
import type {
  TotalStats,
  WeekRow,
  ReplyRow,
  PlatformSentRow,
  PlatformReplyRow,
  InterestedContactRow,
} from "@/types/dashboard";

// All queries below are ported near-verbatim from dashboard.py's
// get_total_stats() / get_weekly_data() / get_recent_replies() /
// get_platform_stats() / get_interested_contacts() — same tables
// (contacts/emails/replies/conversations), same shapes, not redesigned.
// Postgres COUNT(*)/SUM(...) return bigint, which node drivers surface as
// strings to avoid precision loss — every count is wrapped in Number(...)
// below (safe here: contact/email volumes are far under
// Number.MAX_SAFE_INTEGER).

export async function getTotalStats(): Promise<TotalStats> {
  const [
    contactsRows,
    sentRows,
    newVsFollowupRows,
    deliveredRows,
    openedRows,
    clickedRows,
    bouncedRows,
    repliesRows,
    interestedRows,
    conversationsRows,
  ] = await Promise.all([
    sql`SELECT COUNT(*) AS c FROM contacts`,
    sql`SELECT COUNT(*) AS c FROM emails`,
    sql`
      WITH ranked AS (
        SELECT id,
               ROW_NUMBER() OVER (PARTITION BY contact_email ORDER BY sent_at) AS seq
        FROM emails
      )
      SELECT
        COALESCE(SUM(CASE WHEN seq = 1 THEN 1 ELSE 0 END), 0) AS new_sent,
        COALESCE(SUM(CASE WHEN seq > 1 THEN 1 ELSE 0 END), 0) AS followup_sent
      FROM ranked
    `,
    sql`SELECT COUNT(*) AS c FROM emails WHERE delivered_at IS NOT NULL`,
    sql`SELECT COUNT(*) AS c FROM emails WHERE opened_at IS NOT NULL`,
    sql`SELECT COUNT(*) AS c FROM emails WHERE clicked_at IS NOT NULL`,
    sql`SELECT COUNT(*) AS c FROM emails WHERE bounce_type IS NOT NULL`,
    sql`SELECT COUNT(*) AS c FROM replies`,
    sql`SELECT COUNT(*) AS c FROM replies WHERE is_interested = true`,
    sql`SELECT COUNT(*) AS c FROM conversations`,
  ]);

  return {
    contacts: Number(contactsRows[0].c),
    sent: Number(sentRows[0].c),
    newSent: Number(newVsFollowupRows[0].new_sent),
    followupSent: Number(newVsFollowupRows[0].followup_sent),
    delivered: Number(deliveredRows[0].c),
    opened: Number(openedRows[0].c),
    clicked: Number(clickedRows[0].c),
    bounced: Number(bouncedRows[0].c),
    replies: Number(repliesRows[0].c),
    interested: Number(interestedRows[0].c),
    conversations: Number(conversationsRows[0].c),
  };
}

export async function getWeeklyData(numWeeks: number): Promise<WeekRow[]> {
  const ranges = getWeekRanges(numWeeks); // oldest first

  const rows = await Promise.all(
    ranges.map(async (r) => {
      const [sentRows, repliesRows, interestedRows] = await Promise.all([
        sql`
          WITH ranked AS (
            SELECT id, sent_at,
                   ROW_NUMBER() OVER (PARTITION BY contact_email ORDER BY sent_at) AS seq
            FROM emails
          )
          SELECT
            COALESCE(SUM(CASE WHEN seq = 1 THEN 1 ELSE 0 END), 0) AS new_sent,
            COALESCE(SUM(CASE WHEN seq > 1 THEN 1 ELSE 0 END), 0) AS followup_sent
          FROM ranked
          WHERE sent_at >= ${r.weekStart} AND sent_at <= ${r.weekEnd}
        `,
        sql`
          SELECT COUNT(*) AS c FROM replies
          WHERE replied_at >= ${r.weekStart} AND replied_at <= ${r.weekEnd}
        `,
        sql`
          SELECT COUNT(*) AS c FROM replies
          WHERE replied_at >= ${r.weekStart} AND replied_at <= ${r.weekEnd}
            AND is_interested = true
        `,
      ]);

      const newSent = Number(sentRows[0].new_sent);
      const followupSent = Number(sentRows[0].followup_sent);

      const row: WeekRow = {
        label: r.label,
        weekNum: r.weekNum,
        year: r.year,
        sent: newSent + followupSent,
        newSent,
        followupSent,
        replies: Number(repliesRows[0].c),
        interested: Number(interestedRows[0].c),
      };
      return row;
    })
  );

  return rows; // already oldest-first, matches dashboard.py's list(reversed(weeks))
}

export async function getRecentReplies(limit = 10): Promise<ReplyRow[]> {
  const rows = await sql`
    SELECT e.contact_email, r.replied_at, r.is_interested, c.name
    FROM replies r
    JOIN emails e ON r.email_id = e.id
    LEFT JOIN contacts c ON e.contact_email = c.email
    ORDER BY r.replied_at DESC
    LIMIT ${limit}
  `;

  return rows.map((row) => ({
    email: row.contact_email as string,
    repliedAt: row.replied_at ? new Date(row.replied_at as string).toISOString() : null,
    interested: row.is_interested as boolean,
    name: (row.name as string | null) || (row.contact_email as string).split("@")[0],
  }));
}

export async function getPlatformStats(): Promise<{
  sent: PlatformSentRow[];
  replies: PlatformReplyRow[];
}> {
  const [sentRows, replyRows] = await Promise.all([
    sql`
      SELECT c.source_platform, COUNT(*) AS sent,
             SUM(CASE WHEN e.opened_at IS NOT NULL THEN 1 ELSE 0 END) AS opened
      FROM emails e JOIN contacts c ON c.email = e.contact_email
      GROUP BY c.source_platform ORDER BY sent DESC
    `,
    sql`
      SELECT c.source_platform, r.is_interested, COUNT(*) AS c
      FROM replies r
      JOIN emails e ON e.id = r.email_id
      JOIN contacts c ON c.email = e.contact_email
      GROUP BY c.source_platform, r.is_interested
    `,
  ]);

  return {
    sent: sentRows.map((row) => ({
      platform: (row.source_platform as string | null) || "unknown",
      sent: Number(row.sent),
      opened: Number(row.opened),
    })),
    replies: replyRows.map((row) => ({
      platform: (row.source_platform as string | null) || "unknown",
      isInterested: row.is_interested as boolean,
      count: Number(row.c),
    })),
  };
}

export async function getInterestedContacts(): Promise<InterestedContactRow[]> {
  const rows = await sql`
    SELECT c.name, c.email, c.conference, c.source_platform, r.replied_at
    FROM replies r
    JOIN emails e ON e.id = r.email_id
    JOIN contacts c ON c.email = e.contact_email
    WHERE r.is_interested = true
    ORDER BY r.replied_at DESC
  `;

  return rows.map((row) => {
    const repliedAt = row.replied_at ? new Date(row.replied_at as string) : null;
    return {
      name: row.name as string,
      email: row.email as string,
      conference: (row.conference as string | null) || "",
      platform: (row.source_platform as string | null) || "",
      repliedAt: repliedAt
        ? `${repliedAt.getUTCFullYear()}-${String(repliedAt.getUTCMonth() + 1).padStart(
            2,
            "0"
          )}-${String(repliedAt.getUTCDate()).padStart(2, "0")}`
        : "",
    };
  });
}
