// Shared responsive knobs for the Recharts charts. These are props rather than
// CSS, so they're driven by useIsNarrow() instead of a media query.

export const CHART_HEIGHT = (isNarrow: boolean) => (isNarrow ? 240 : 320);

// "Jul 27–Aug 2" -> "Jul 27". Four full range labels won't fit across a phone
// without colliding, and dropping ticks entirely would be worse than showing
// just the week's start date. En dash (U+2013) — matches src/lib/weeks.ts.
export function shortWeekLabel(label: string): string {
  return label.split("–")[0];
}
