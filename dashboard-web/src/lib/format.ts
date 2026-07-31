export function formatInt(n: number): string {
  return n.toLocaleString("en-US");
}

export function formatPct(n: number, digits = 1): string {
  return `${n.toFixed(digits)}%`;
}

export function formatSignedPct(n: number, digits = 1): string {
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(digits)}pp`;
}

export function formatShortDate(d: Date | string | null): string {
  if (!d) return "";
  const date = typeof d === "string" ? new Date(d) : d;
  const mm = (date.getUTCMonth() + 1).toString().padStart(2, "0");
  const dd = date.getUTCDate().toString().padStart(2, "0");
  return `${mm}/${dd}`;
}

export function formatISODate(d: Date | string | null): string {
  if (!d) return "";
  const date = typeof d === "string" ? new Date(d) : d;
  const yyyy = date.getUTCFullYear();
  const mm = (date.getUTCMonth() + 1).toString().padStart(2, "0");
  const dd = date.getUTCDate().toString().padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}
