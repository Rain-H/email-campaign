"use client";

interface TooltipPayloadItem {
  name?: string;
  value?: number | string;
  color?: string;
  dataKey?: string | number;
}

interface ChartTooltipProps {
  active?: boolean;
  label?: string | number;
  payload?: TooltipPayloadItem[];
}

// Custom tooltip: value leads (Strong/high-contrast), series name follows
// (secondary ink); each row keyed with a short line stroke of the series
// color rather than a filled box (line-key, not a box, per dataviz skill).
export default function ChartTooltip({ active, label, payload }: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div
      style={{
        background: "var(--surface-1)",
        border: "1px solid var(--border)",
        borderRadius: 6,
        padding: "8px 10px",
        boxShadow: "0 2px 8px rgba(0,0,0,0.12)",
        fontSize: 13,
      }}
    >
      {label !== undefined && (
        <div style={{ color: "var(--text-muted)", marginBottom: 4 }}>{label}</div>
      )}
      {payload.map((item, i) => (
        <div
          key={i}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            lineHeight: 1.6,
          }}
        >
          <span
            aria-hidden
            style={{
              display: "inline-block",
              width: 12,
              height: 2,
              background: item.color,
              flexShrink: 0,
            }}
          />
          <span
            className="tabular-nums"
            style={{ color: "var(--text-primary)", fontWeight: 600 }}
          >
            {item.value}
          </span>
          <span style={{ color: "var(--text-secondary)" }}>{item.name}</span>
        </div>
      ))}
    </div>
  );
}
