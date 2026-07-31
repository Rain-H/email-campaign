"use client";

import { Funnel, FunnelChart, LabelList, ResponsiveContainer, Tooltip } from "recharts";
import ChartCard from "./ChartCard";
import ChartTableFallback from "./ChartTableFallback";
import ChartTooltip from "./ChartTooltip";
import { FUNNEL_RAMP } from "./palette";

interface FunnelStats {
  sent: number;
  opened: number;
  replies: number;
  interested: number;
}

export default function ConversionFunnelChart({ stats }: { stats: FunnelStats }) {
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
    <ResponsiveContainer width="100%" height={320}>
      <FunnelChart>
        <Tooltip content={<ChartTooltip />} />
        <Funnel dataKey="value" data={data} isAnimationActive={false}>
          <LabelList
            position="right"
            dataKey="name"
            fill="var(--text-primary)"
            stroke="none"
            fontSize={13}
          />
          <LabelList
            position="left"
            dataKey="pctLabel"
            fill="var(--text-secondary)"
            stroke="none"
            fontSize={12}
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
