interface StatCardProps {
  icon?: string;
  label: string;
  value: string;
  delta?: { text: string; tone?: "good" | "critical" | "neutral" };
  caption?: string;
}

const TONE_COLOR: Record<string, string> = {
  good: "var(--status-good)",
  critical: "var(--status-critical)",
  neutral: "var(--text-secondary)",
};

// Stat-tile contract (dataviz skill): label (sentence case, no trailing
// colon) · value (semibold) · delta (optional, signed, color = direction ×
// whether up is good) · caption. Value uses proportional figures (not
// tabular-nums — that's reserved for table/axis columns).
export default function StatCard({ icon, label, value, delta, caption }: StatCardProps) {
  return (
    <div
      style={{
        background: "var(--surface-1)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: 14,
        display: "flex",
        flexDirection: "column",
        gap: 4,
        minWidth: 0,
      }}
    >
      <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
        {icon ? `${icon} ` : ""}
        {label}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ fontSize: 24, fontWeight: 600, color: "var(--text-primary)" }}>
          {value}
        </span>
        {delta && (
          <span style={{ fontSize: 13, color: TONE_COLOR[delta.tone ?? "neutral"] }}>
            {delta.text}
          </span>
        )}
      </div>
      {caption && (
        <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.4 }}>
          {caption}
        </div>
      )}
    </div>
  );
}
