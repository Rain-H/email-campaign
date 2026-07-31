# Email Campaign Dashboard (web)

Next.js port of the repo-root `dashboard.py` Streamlit dashboard, built to deploy on
Vercel instead of Streamlit Community Cloud (Streamlit needs a persistent server
process; Vercel is serverless). Same production Neon Postgres DB, read-only.

No auth — this is a public URL. It shows real contact names/emails from the campaign.
Auto-refreshes every ~45s (`src/lib/config.ts`); no push/WebSocket realtime.

## Local dev

```bash
npm install
cp .env.example .env.local   # paste the real DATABASE_URL from the repo-root .env
npm run dev
```

Open http://localhost:3000. Cross-check a few totals (total sent, total replies,
total interested) against `streamlit run ../dashboard.py` or a manual
`SELECT COUNT(*) FROM emails` before trusting the rest of the page.

```bash
curl localhost:3000/api/health   # {"ok":true,"latencyMs":<n>}
npm run build && npm run lint    # before deploying
```

## Deploy (Vercel)

1. In Vercel project settings, set **Root Directory** to `dashboard-web` (this app is
   nested in a subdirectory of the repo, not at the repo root).
2. Add the `DATABASE_URL` environment variable (Project Settings → Environment
   Variables), for both Production and Preview.
3. Connect the GitHub repo for auto-deploy on push to `main`, or deploy manually:
   ```bash
   npx vercel link      # Root Directory: dashboard-web
   npx vercel env add DATABASE_URL production
   npx vercel --prod
   ```
4. On the live URL: confirm all sections render real data, hit `/api/health`, and
   watch for a re-render roughly every 45s without a full page reload.

`vercel.json` pins the function region to `iad1` (us-east-1) to co-locate with the
Neon DB host — matters here since `getWeeklyData()` fans out to several small
per-week queries.

## What's ported from `dashboard.py`

All 5 query functions (`getTotalStats`, `getWeeklyData`, `getRecentReplies`,
`getPlatformStats`, `getInterestedContacts` in `src/lib/queries.ts`) are near-verbatim
ports of the same-named Python functions — same tables, same SQL shape. The one
non-trivial piece is `src/lib/weeks.ts`, which re-implements `dashboard.py`'s UTC
ISO-week bucketing (including its `week -= 52` year-rollover simplification,
deliberately not "fixed" so week boundaries match the existing dashboard exactly).

## Optional hardening

This DB URL sits in a Vercel env var backing a public, unauthenticated page. Consider
creating a dedicated read-only Postgres role in Neon instead of using the `emails`/
`contacts` owner role from the root `.env`:

```sql
CREATE ROLE dashboard_reader WITH LOGIN PASSWORD '...';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dashboard_reader;
```

Zero functional cost (the app never writes) — removes an entire class of future risk.
