// Cold email industry benchmarks (2026 snapshot), ported as-is from dashboard.py.
// Sources:
//   - b2bdataindex.com/benchmarks/cold-email-2026/
//   - mailshake.com/blog/cold-email-benchmarks-2026/
//   - prospeo.io/s/cold-email-click-through-rate
// Update once a year.
export const BENCHMARKS = {
  openRate: { median: 22.0, tech: 26.0 },
  clickRate: { median: 3.0, tech: 3.0 },
  replyRate: { median: 4.0, tech: 5.0 },
  bounceRate: { target: 2.0 },
};
