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
import type { WeekRow } from "@/types/dashboard";
import ChartCard from "./ChartCard";
import ChartTableFallback from "./ChartTableFallback";
import ChartTooltip from "./ChartTooltip";
import { COLOR } from "./palette";

export default function WeeklyRepliesChart({ data }: { data: WeekRow[] }) {
  const chart = (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} barGap={2} barCategoryGap="20%">
        <CartesianGrid vertical={false} stroke={COLOR.gridline} strokeWidth={1} />
        <XAxis
          dataKey="week"
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
        <Bar dataKey="replies" name="Replies" fill={COLOR.series1} radius={[4, 4, 0, 0]} maxBarSize={24} />
        <Bar
          dataKey="interested"
          name="Interested"
          fill={COLOR.series2}
          radius={[4, 4, 0, 0]}
          maxBarSize={24}
        />
      </BarChart>
    </ResponsiveContainer>
  );

  const table = (
    <ChartTableFallback
      rows={data.map((d) => ({
        Week: d.week,
        Replies: d.replies,
        Interested: d.interested,
      }))}
      columns={[
        { key: "Week", label: "Week" },
        { key: "Replies", label: "Replies", align: "right" },
        { key: "Interested", label: "Interested", align: "right" },
      ]}
    />
  );

  return <ChartCard title="Weekly Replies & Interested" chart={chart} table={table} />;
}
