import type { TotalStats } from "@/types/dashboard";
import { BENCHMARKS } from "@/lib/benchmarks";
import { formatInt, formatPct, formatSignedPct } from "@/lib/format";
import StatCard from "./StatCard";

export default function StatCardRow({ total }: { total: TotalStats }) {
  const replyRate = total.sent > 0 ? (total.replies / total.sent) * 100 : 0;
  const openRate = total.sent > 0 ? (total.opened / total.sent) * 100 : 0;
  const clickRate = total.sent > 0 ? (total.clicked / total.sent) * 100 : 0;
  const bounceRate = total.sent > 0 ? (total.bounced / total.sent) * 100 : 0;
  const interestShare = total.replies > 0 ? (total.interested / total.replies) * 100 : 0;

  const bm = BENCHMARKS;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
        gap: 12,
      }}
    >
      <StatCard
        icon="📤"
        label="Sent"
        value={formatInt(total.sent)}
        caption={`New: ${formatInt(total.newSent)} · Follow-up: ${formatInt(total.followupSent)}`}
      />
      <StatCard
        icon="📭"
        label="Bounced"
        value={formatInt(total.bounced)}
        delta={{
          text: `-${formatPct(bounceRate)}`,
          tone: bounceRate > bm.bounceRate.target ? "critical" : "good",
        }}
        caption={`Industry target < ${bm.bounceRate.target.toFixed(0)}% · You ${formatPct(bounceRate)}`}
      />
      <StatCard
        icon="👁"
        label="Open Rate"
        value={formatPct(openRate)}
        delta={{ text: `${formatInt(total.opened)} opened`, tone: "neutral" }}
        caption={`Industry median ${bm.openRate.median.toFixed(
          0
        )}% · ⚠ inflated by Apple Mail Privacy Protection — see Click Rate`}
      />
      <StatCard
        icon="🖱"
        label="Click Rate"
        value={formatPct(clickRate)}
        delta={{ text: `${formatInt(total.clicked)} clicked`, tone: "neutral" }}
        caption={`Industry median ${bm.clickRate.median.toFixed(0)}% · You ${formatSignedPct(
          clickRate - bm.clickRate.median
        )} (real engagement signal)`}
      />
      <StatCard
        icon="📬"
        label="Replies"
        value={formatInt(total.replies)}
        caption={`${formatInt(total.interested)} interested of ${formatInt(total.replies)}`}
      />
      <StatCard
        icon="📊"
        label="Reply Rate"
        value={formatPct(replyRate)}
        caption={`Industry median ${bm.replyRate.median.toFixed(0)}% (Tech ${bm.replyRate.tech.toFixed(
          0
        )}%) · You ${formatSignedPct(replyRate - bm.replyRate.median)}`}
      />
      <StatCard
        icon="✅"
        label="Interested"
        value={formatInt(total.interested)}
        caption={`${interestShare.toFixed(0)}% of replies`}
      />
    </div>
  );
}
