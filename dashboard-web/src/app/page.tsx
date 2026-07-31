import {
  getInterestedContacts,
  getPlatformStats,
  getRecentReplies,
  getTotalStats,
  getWeeklyData,
} from "@/lib/queries";
import { WEEKS_SHOWN } from "@/lib/config";
import AutoRefresh from "@/components/AutoRefresh";
import RefreshButton from "@/components/RefreshButton";
import StatCardRow from "@/components/StatCardRow";
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

export default async function DashboardPage() {
  const [total, weeklyData, recentReplies, platformStats, interestedContacts] =
    await Promise.all([
      getTotalStats(),
      getWeeklyData(WEEKS_SHOWN),
      getRecentReplies(10),
      getPlatformStats(),
      getInterestedContacts(),
    ]);

  return (
    <main className="page">
      <AutoRefresh />

      <div className="page-header">
        <h1 className="page-title">📧 Email Campaign Dashboard</h1>
        <RefreshButton />
      </div>

      <StatCardRow total={total} />

      <section className="section">
        <h2 className="section-title">
          📈 Weekly Trends (last {WEEKS_SHOWN} weeks)
        </h2>
        <div className="split-grid">
          <WeeklySentChart data={weeklyData} />
          <WeeklyRepliesChart data={weeklyData} />
        </div>
      </section>

      <section className="section split-grid">
        <div>
          <h2 className="section-title">🔄 Conversion Funnel</h2>
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
          <h2 className="section-title">📡 Platform Breakdown</h2>
          <PlatformBreakdownChart data={platformStats.sent} />
        </div>
      </section>

      <section className="section">
        <h2 className="section-title">✅ Interested Contacts</h2>
        <InterestedContactsTable rows={interestedContacts} />
      </section>

      <section className="section split-grid">
        <div>
          <h2 className="section-title">📋 Recent Replies</h2>
          <RecentRepliesList replies={recentReplies} />
        </div>
        <div>
          <h2 className="section-title">📊 Weekly Breakdown</h2>
          <WeeklyBreakdownTable data={weeklyData} />
        </div>
      </section>
    </main>
  );
}
