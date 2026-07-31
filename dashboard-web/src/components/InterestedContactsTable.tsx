import type { CSSProperties } from "react";
import type { InterestedContactRow } from "@/types/dashboard";

export default function InterestedContactsTable({ rows }: { rows: InterestedContactRow[] }) {
  if (rows.length === 0) {
    return (
      <div style={{ color: "var(--text-muted)", fontSize: 14 }}>
        No interested replies yet
      </div>
    );
  }

  return (
    <div className="table-scroll">
      <table style={{ fontSize: 13 }}>
        <thead>
          <tr>
            {["Name", "Email", "Conference", "Platform", "Reply Date"].map((h) => (
              <th
                key={h}
                style={{
                  textAlign: "left",
                  color: "var(--text-muted)",
                  fontWeight: 500,
                  borderBottom: "1px solid var(--gridline)",
                  padding: "6px 10px",
                  whiteSpace: "nowrap",
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td style={cellStyle}>{r.name}</td>
              <td style={cellStyle}>{r.email}</td>
              <td style={cellStyle}>{r.conference}</td>
              <td style={cellStyle}>{r.platform}</td>
              <td className="tabular-nums" style={cellStyle}>
                {r.repliedAt}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const cellStyle: CSSProperties = {
  color: "var(--text-primary)",
  borderBottom: "1px solid var(--gridline)",
  padding: "6px 10px",
  whiteSpace: "nowrap",
};
