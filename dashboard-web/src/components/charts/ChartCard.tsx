"use client";

import { useState, type ReactNode } from "react";

interface ChartCardProps {
  title: string;
  caption?: string;
  chart: ReactNode;
  table: ReactNode;
}

// Shared wrapper: title + optional caption, a chart/table toggle (every
// chart ships a table fallback — dataviz skill's accessibility pass), and a
// consistent card surface.
export default function ChartCard({ title, caption, chart, table }: ChartCardProps) {
  const [showTable, setShowTable] = useState(false);

  return (
    <figure
      style={{
        background: "var(--surface-1)",
        border: `1px solid var(--border)`,
        borderRadius: 8,
        padding: 12,
        margin: 0,
        // lets the card shrink inside its grid track instead of forcing the
        // track wider than a phone viewport
        minWidth: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 8,
          marginBottom: 4,
        }}
      >
        <figcaption style={{ fontWeight: 600, color: "var(--text-primary)" }}>
          {title}
        </figcaption>
        <button
          type="button"
          onClick={() => setShowTable((v) => !v)}
          style={{
            background: "none",
            border: "1px solid var(--border)",
            borderRadius: 4,
            // roomy enough to be a comfortable touch target, not just a mouse one
            padding: "6px 10px",
            fontSize: 12,
            color: "var(--text-secondary)",
            cursor: "pointer",
            whiteSpace: "nowrap",
          }}
        >
          {showTable ? "View chart" : "View as table"}
        </button>
      </div>
      {caption && (
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
          {caption}
        </div>
      )}
      {showTable ? table : chart}
    </figure>
  );
}
