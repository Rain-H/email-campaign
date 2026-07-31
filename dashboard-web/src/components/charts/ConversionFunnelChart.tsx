"use client";

import { Funnel, FunnelChart, LabelList, ResponsiveContainer, Tooltip } from "recharts";
import { useIsNarrow } from "@/lib/useIsNarrow";
import ChartCard from "./ChartCard";
import ChartTableFallback from "./ChartTableFallback";
import ChartTooltip from "./ChartTooltip";
import { FUNNEL_RAMP } from "./palette";
import { CHART_HEIGHT } from "./responsive";

interface FunnelStats {
  sent: number;
  opened: number;
  replies: number;
  interested: number;
}

export default function ConversionFunnelChart({ stats }: { stats: FunnelStats }) {
  const isNarrow = useIsNarrow();

  const stages = [
    { name: "Sent", value: stats.sent },
    { name: "Opened", value: stats.opened },
    { name: "Replied", value: stats.replies },
    { name: "Interested", value: stats.interested },
  ];
  const initial = stages[0].value || 1;
  const data = stages.map((s, i) => ({
    ...s,
    fill: FUNNEL_RAMP[i],
    pctLabel: `${s.value.toLocaleString()} (${((s.value / initial) * 100).toFixed(0)}%)`,
  }));

  const chart = (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT(isNarrow)}>
      {/* The stage name sits to the right of each trapezoid and the
          count/percentage to its left, so the plot area has to leave room for
          both — without these margins the outer labels are drawn past the
          container edge and clipped once it gets narrow. */}
      <FunnelChart margin={{ top: 8, bottom: 8, left: isNarrow ? 78 : 96, right: isNarrow ? 60 : 76 }}>
        <Tooltip content={<ChartTooltip />} />
        <Funnel dataKey="value" data={data} isAnimationActive={false}>
          <LabelList
            position="right"
            dataKey="name"
            fill="var(--text-primary)"
            stroke="none"
            fontSize={isNarrow ? 12 : 13}
          />
          <LabelList
            position="left"
            dataKey="pctLabel"
            fill="var(--text-secondary)"
            stroke="none"
            fontSize={isNarrow ? 11 : 12}
          />
        </Funnel>
      </FunnelChart>
    </ResponsiveContainer>
  );

  const table = (
    <ChartTableFallback
      rows={data.map((d) => ({
        Stage: d.name,
        Value: d.value,
        "% of Sent": `${((d.value / initial) * 100).toFixed(0)}%`,
      }))}
      columns={[
        { key: "Stage", label: "Stage" },
        { key: "Value", label: "Value", align: "right" },
        { key: "% of Sent", label: "% of Sent", align: "right" },
      ]}
    />
  );

  return <ChartCard title="Conversion Funnel" chart={chart} table={table} />;
}
