# Email Campaign — Safety Rules

These rules apply to every session in this project, regardless of which skill is active. They were migrated from `.cursor/rules/*.mdc` (Cursor's `alwaysApply: true` rules) — Claude Code doesn't have a separate always-apply rule file, so `CLAUDE.md` is the equivalent.

## Sending emails requires explicit confirmation

- NEVER execute `send_postmark.py --send`, `send_followup.py --send`, or any email-sending command unless the user says exactly **"Please send email"**.
- "send", "go ahead", "do it", "yes" are NOT sufficient — ask them to confirm with the exact phrase.
- Always show a dry run (preview) first and wait for confirmation before adding `--send`.

## Never use production data by accident

- Any data file other than `test_data.csv` is production data (e.g. any `crawled_easychair_*.json/csv`, `crawled_edas*.json/csv`, `unsent_chairs.csv`).
- Don't use a production file as email recipients unless the user explicitly names it.
- If the user says "send emails" without naming a data source, default to `test_data.csv`.

## Always use `--test` with test data

- When using `test_data.csv`, always pass `--test` so results land in `crm_test`, not the production `crm` database.
- Applies to `send_postmark.py --test`, `send_followup.py --test`, `crm_check.py --test`, `backfill_email_bodies.py --test`.
- Never write test email results to the production database.

## Process safety for long-running scripts (crawlers, senders, servers)

1. **Before starting**: check no matching process is already running — `ps aux | grep <script_name> | grep -v grep`. If one exists, ask the user whether to kill it first. Never run two instances of the same script in parallel unless explicitly asked.
2. **Email sending is single-instance only**: `send_postmark.py --send` and `send_followup.py --send` must never run concurrently with themselves.
3. **Track PIDs explicitly** when backgrounding a command; kill by exact PID, and verify with `ps -p <PID>` that it's actually gone before retrying (escalate to `kill -9` if it lingers).
4. **On connection errors** (`Connection error`, `OpenAI connection error`, `Cannot connect to proxy`, repeated request failures) during a crawl: stop immediately, kill and verify the process is dead, fix connectivity, then restart from resume/retry mode. Don't keep crawling through connection errors.

## Verifying email sends: know Postmark's limits before trusting it

- If a send command shows no output or looks stuck, don't assume nothing was sent — check Postmark before retrying (see `email-crm` skill for bulk vs per-contact sync).
- **The Postmark server is shared with PaperFox product emails** (`notifications@paperfox.ai` sends things like "Review Submitted"). Cold campaign emails come from `rain@paperfox.ai` (`POSTMARK_SENDER_EMAIL`). When querying `/messages/outbound`, always filter by sender/recipient — never assume all messages on the account are cold-campaign emails.
- **Postmark only retains outbound message activity/content for ~45 days** (confirmed 2026-07-24: a message from 2026-05-19, 66 days old, returned `422 "This message was not found"` from `/messages/outbound/{id}/details`). Anything older is gone from Postmark's side — the project's own `emails` table in PostgreSQL is the only surviving record past that window. Don't expect Postmark to be able to confirm or deny old sends.

## Related skills

- `postmark-cold-email` — sending the initial campaign
- `first-follow-up` — forwarding follow-ups to unreplied contacts
- `email-crm` — syncing delivery/open/click/reply status
- `reply-to-replies` — drafting replies to inbound responses
- `conference-crawling` / `edas-crawling` — building the recipient lists these rules protect
- `weekly-stats` — reporting on campaign performance
