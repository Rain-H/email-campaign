// Role-based references into the CSS custom properties defined in
// globals.css (dataviz skill palette). Using var(...) directly as SVG
// fill/stroke values means light/dark switching is automatic via the CSS
// cascade — no JS media-query plumbing needed.
export const COLOR = {
  series1: "var(--series-1)",
  series2: "var(--series-2)",
  series3: "var(--series-3)",

  seq250: "var(--seq-250)",
  seq350: "var(--seq-350)",
  seq450: "var(--seq-450)",
  seq550: "var(--seq-550)",

  statusGood: "var(--status-good)",
  statusWarning: "var(--status-warning)",
  statusSerious: "var(--status-serious)",
  statusCritical: "var(--status-critical)",

  gridline: "var(--gridline)",
  baseline: "var(--baseline)",
  textPrimary: "var(--text-primary)",
  textSecondary: "var(--text-secondary)",
  textMuted: "var(--text-muted)",
  surface1: "var(--surface-1)",
};

// Funnel stage ramp, light→dark, one hue (ordinal use — validated with
// --ordinal in both light and dark modes, see dataviz skill validator).
export const FUNNEL_RAMP = [COLOR.seq250, COLOR.seq350, COLOR.seq450, COLOR.seq550];
