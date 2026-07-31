import type { WeekRow } from "@/types/dashboard";
import ChartTableFallback from "./charts/ChartTableFallback";

export default function WeeklyBreakdownTable({ data }: { data: WeekRow[] }) {
  return (
    <ChartTableFallback
      rows={data.map((d) => ({
        Week: d.week,
        Start: d.weekStart,
        New: d.newSent,
        "Follow-up": d.followupSent,
        Sent: d.sent,
        Replies: d.replies,
        Interested: d.interested,
      }))}
      columns={[
        { key: "Week", label: "Week" },
        { key: "Start", label: "Start" },
        { key: "New", label: "New", align: "right" },
        { key: "Follow-up", label: "Follow-up", align: "right" },
        { key: "Sent", label: "Sent", align: "right" },
        { key: "Replies", label: "Replies", align: "right" },
        { key: "Interested", label: "Interested", align: "right" },
      ]}
    />
  );
}
