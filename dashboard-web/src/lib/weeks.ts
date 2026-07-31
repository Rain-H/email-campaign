// Port of dashboard.py's get_weekly_data() week-bucketing math.
//
// dashboard.py deliberately buckets in UTC (not local time) because sent_at/
// replied_at are stored as naive-UTC timestamps — bucketing from local time
// would misfile emails sent near a week boundary whenever the host isn't UTC.
// Everything here uses Date.UTC(...) / getUTC*() exclusively for the same
// reason; never mix in a local-time Date method.
//
// This is a literal port of the Python arithmetic (including its `week -= 52`
// year-rollover simplification, which is not fully correct for ISO years with
// 53 weeks) — deliberately not "fixed", so week boundaries match the existing
// Streamlit dashboard's numbers exactly rather than silently diverging.

export interface WeekRange {
  week: string; // "W30"
  weekNum: number;
  year: number;
  weekStartLabel: string; // "07/24"
  weekStart: Date;
  weekEnd: Date;
}

function isoWeekOf(date: Date): { isoYear: number; isoWeek: number } {
  const d = new Date(
    Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate())
  );
  // ISO weekday: Monday=1 ... Sunday=7 (JS getUTCDay() is Sunday=0 ... Saturday=6)
  const isoDayNum = ((d.getUTCDay() + 6) % 7) + 1;
  // Shift to this week's Thursday — the ISO week number is the Thursday's week.
  d.setUTCDate(d.getUTCDate() + 4 - isoDayNum);
  const isoYear = d.getUTCFullYear();
  const yearStart = Date.UTC(isoYear, 0, 1);
  const isoWeek = Math.ceil((d.getTime() - yearStart) / 86_400_000 / 7) + 1;
  return { isoYear, isoWeek };
}

function pad2(n: number): string {
  return n.toString().padStart(2, "0");
}

export function getWeekRanges(numWeeks: number): WeekRange[] {
  const now = new Date();
  const { isoYear: currentYear, isoWeek: currentWeek } = isoWeekOf(now);

  const ranges: WeekRange[] = [];
  for (let i = 0; i < numWeeks; i++) {
    let week = currentWeek - i;
    let year = currentYear;
    if (week <= 0) {
      week += 52;
      year -= 1;
    }

    const jan4 = Date.UTC(year, 0, 4);
    const jan4Weekday = (new Date(jan4).getUTCDay() + 6) % 7; // Monday=0..Sunday=6
    const startOfWeek1 = jan4 - jan4Weekday * 86_400_000;
    const weekStartMs = startOfWeek1 + (week - 1) * 7 * 86_400_000;
    const weekEndMs =
      weekStartMs + 6 * 86_400_000 + 23 * 3_600_000 + 59 * 60_000 + 59 * 1_000;

    const weekStart = new Date(weekStartMs);
    const weekEnd = new Date(weekEndMs);

    ranges.push({
      week: `W${week}`,
      weekNum: week,
      year,
      weekStartLabel: `${pad2(weekStart.getUTCMonth() + 1)}/${pad2(
        weekStart.getUTCDate()
      )}`,
      weekStart,
      weekEnd,
    });
  }

  return ranges.reverse(); // oldest first, matches dashboard.py's list(reversed(weeks))
}
