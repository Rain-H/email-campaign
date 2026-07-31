interface Column<T> {
  key: keyof T;
  label: string;
  align?: "left" | "right";
}

interface ChartTableFallbackProps<T> {
  rows: T[];
  columns: Column<T>[];
}

export default function ChartTableFallback<T extends Record<string, unknown>>({
  rows,
  columns,
}: ChartTableFallbackProps<T>) {
  return (
    <div className="table-scroll">
      <table style={{ fontSize: 13 }}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={String(col.key)}
                style={{
                  textAlign: col.align ?? "left",
                  color: "var(--text-muted)",
                  fontWeight: 500,
                  borderBottom: "1px solid var(--gridline)",
                  padding: "6px 8px",
                  whiteSpace: "nowrap",
                }}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((col) => (
                <td
                  key={String(col.key)}
                  className="tabular-nums"
                  style={{
                    textAlign: col.align ?? "left",
                    color: "var(--text-primary)",
                    borderBottom: "1px solid var(--gridline)",
                    padding: "6px 8px",
                    whiteSpace: "nowrap",
                  }}
                >
                  {String(row[col.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
