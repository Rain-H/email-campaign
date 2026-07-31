"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PlatformSentRow } from "@/types/dashboard";
import ChartCard from "./ChartCard";
import ChartTableFallback from "./ChartTableFallback";
import ChartTooltip from "./ChartTooltip";
import { COLOR } from "./palette";

export default function PlatformBreakdownChart({ data }: { data: PlatformSentRow[] }) {
  const chart = (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} barGap={2} barCategoryGap="20%">
        <CartesianGrid vertical={false} stroke={COLOR.gridline} strokeWidth={1} />
        <XAxis
          dataKey="platform"
          tick={{ fill: "var(--text-muted)", fontSize: 12 }}
          axisLine={{ stroke: COLOR.baseline }}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: "var(--text-muted)", fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          allowDecimals={false}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--gridline)" }} />
        <Legend
          wrapperStyle={{ fontSize: 12, color: "var(--text-secondary)" }}
          itemSorter={null}
        />
        <Bar dataKey="sent" name="Sent" fill={COLOR.series1} radius={[4, 4, 0, 0]} maxBarSize={24} />
        <Bar dataKey="opened" name="Opened" fill={COLOR.series2} radius={[4, 4, 0, 0]} maxBarSize={24} />
      </BarChart>
    </ResponsiveContainer>
  );

  const table = (
    <ChartTableFallback
      rows={data.map((d) => ({
        Platform: d.platform,
        Sent: d.sent,
        Opened: d.opened,
      }))}
      columns={[
        { key: "Platform", label: "Platform" },
        { key: "Sent", label: "Sent", align: "right" },
        { key: "Opened", label: "Opened", align: "right" },
      ]}
    />
  );

  return <ChartCard title="Platform Breakdown" chart={chart} table={table} />;
}
