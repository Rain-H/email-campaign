import { Suspense } from "react";
import {
  getInterestedContacts,
  getPlatformStats,
  getRecentReplies,
  getTotalStats,
  getWeeklyData,
} from "@/lib/queries";
import { WEEKS_DEFAULT, WEEKS_MAX, WEEKS_MIN } from "@/lib/config";
import AutoRefresh from "@/components/AutoRefresh";
import RefreshButton from "@/components/RefreshButton";
import StatCardRow from "@/components/StatCardRow";
import WeeksSlider from "@/components/WeeksSlider";
import InterestedContactsTable from "@/components/InterestedContactsTable";
import RecentRepliesList from "@/components/RecentRepliesList";
import WeeklyBreakdownTable from "@/components/WeeklyBreakdownTable";
import WeeklySentChart from "@/components/charts/WeeklySentChart";
import WeeklyRepliesChart from "@/components/charts/WeeklyRepliesChart";
import ConversionFunnelChart from "@/components/charts/ConversionFunnelChart";
import PlatformBreakdownChart from "@/components/charts/PlatformBreakdownChart";

// Never serve a cached/static render — every direct load and every
// router.refresh() (manual button + AutoRefresh interval) must re-run the
// queries against the live DB. (cacheComponents is NOT enabled in
// next.config.ts, so this "previous model" route segment config applies.)
export const dynamic = "force-dynamic";
export const revalidate = 0;

function clampWeeks(raw: string | undefined): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return WEEKS_DEFAULT;
  return Math.min(WEEKS_MAX, Math.max(WEEKS_MIN, Math.round(n)));
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ weeks?: string }>;
}) {
  const params = await searchParams;
  const weeks = clampWeeks(params.weeks);

  const [total, weeklyData, recentReplies, platformStats, interestedContacts] =
    await Promise.all([
      getTotalStats(),
      getWeeklyData(weeks),
      getRecentReplies(10),
      getPlatformStats(),
      getInterestedContacts(),
    ]);

  return (
    <main style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 20px 60px" }}>
      <AutoRefresh />

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 20,
        }}
      >
        <h1 style={{ fontSize: 22, fontWeight: 600 }}>📧 Email Campaign Dashboard</h1>
        <RefreshButton />
      </div>

      <StatCardRow total={total} />

      <section style={{ marginTop: 32 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 12,
          }}
        >
          <h2 style={{ fontSize: 16, fontWeight: 600 }}>📈 Weekly Trends</h2>
          <Suspense fallback={null}>
            <WeeksSlider value={weeks} />
          </Suspense>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))",
            gap: 16,
          }}
        >
          <WeeklySentChart data={weeklyData} />
          <WeeklyRepliesChart data={weeklyData} />
        </div>
      </section>

      <section
        style={{
          marginTop: 32,
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))",
          gap: 16,
        }}
      >
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
            🔄 Conversion Funnel
          </h2>
          <ConversionFunnelChart
            stats={{
              sent: total.sent,
              opened: total.opened,
              replies: total.replies,
              interested: total.interested,
            }}
          />
        </div>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
            📡 Platform Breakdown
          </h2>
          <PlatformBreakdownChart data={platformStats.sent} />
        </div>
      </section>

      <section style={{ marginTop: 32 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
          ✅ Interested Contacts
        </h2>
        <InterestedContactsTable rows={interestedContacts} />
      </section>

      <section
        style={{
          marginTop: 32,
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))",
          gap: 16,
        }}
      >
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
            📋 Recent Replies
          </h2>
          <RecentRepliesList replies={recentReplies} />
        </div>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
            📊 Weekly Breakdown
          </h2>
          <WeeklyBreakdownTable data={weeklyData} />
        </div>
      </section>
    </main>
  );
}
