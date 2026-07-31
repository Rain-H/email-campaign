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
import { useIsNarrow } from "@/lib/useIsNarrow";
import ChartCard from "./ChartCard";
import ChartTableFallback from "./ChartTableFallback";
import ChartTooltip from "./ChartTooltip";
import { COLOR } from "./palette";
import { CHART_HEIGHT, shortWeekLabel } from "./responsive";

export default function WeeklySentChart({ data }: { data: WeekRow[] }) {
  const isNarrow = useIsNarrow();

  const chart = (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT(isNarrow)}>
      <BarChart data={data} barGap={2} barCategoryGap="20%">
        <CartesianGrid
          vertical={false}
          stroke={COLOR.gridline}
          strokeWidth={1}
        />
        <XAxis
          dataKey="label"
          tickFormatter={(v: string) => (isNarrow ? shortWeekLabel(v) : v)}
          interval={0}
          tick={{ fill: "var(--text-muted)", fontSize: isNarrow ? 11 : 12 }}
          axisLine={{ stroke: COLOR.baseline }}
          tickLine={false}
        />
        <YAxis
          width={isNarrow ? 32 : undefined}
          tick={{ fill: "var(--text-muted)", fontSize: isNarrow ? 11 : 12 }}
          axisLine={false}
          tickLine={false}
          allowDecimals={false}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--gridline)" }} />
        {/* itemSorter=null: Recharts' default sorts the legend
            alphabetically by label (Follow-up before New) — disable that
            so it follows Bar declaration order instead. */}
        <Legend
          wrapperStyle={{ fontSize: 12, color: "var(--text-secondary)" }}
          itemSorter={null}
        />
        <Bar dataKey="newSent" name="New" fill={COLOR.series1} radius={[4, 4, 0, 0]} maxBarSize={24} />
        <Bar
          dataKey="followupSent"
          name="Follow-up"
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
        Week: d.label,
        New: d.newSent,
        "Follow-up": d.followupSent,
      }))}
      columns={[
        { key: "Week", label: "Week" },
        { key: "New", label: "New", align: "right" },
        { key: "Follow-up", label: "Follow-up", align: "right" },
      ]}
    />
  );

  return <ChartCard title="Weekly Sent (New vs Follow-up)" chart={chart} table={table} />;
}
