# Email Campaign — Safety Rules

These rules apply to every session in this project, regardless of which skill is active. Claude Code has no separate always-apply rule file, so this one is it — anything here is in force for every session, and nothing else needs to opt in.

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

## Never contact a suppressed address

- The `suppressions` table in PostgreSQL is the do-not-contact list. If an
  address is in it, no campaign email, no follow-up, no exceptions.
- It is enforced in three places, and all three must stay: the SQL in
  `crm_db.get_followup_candidates`, and an in-memory re-check in both
  `send_postmark.py` and `send_followup.py` immediately before composing.
  The duplication is on purpose — the in-memory check is the last gate before
  mail leaves, and it covers recipient lists that never touch the candidates
  query, such as a CSV handed to `send_postmark.py`.
- A failed suppression lookup must **abort the send**, never fall back to an
  empty set. Empty reads as "nobody is suppressed" and mails exactly the
  people who asked us to stop.
- Reasons: `opt_out` (asked us to stop), `declined` (said no, including a
  polite "we're happy with EasyChair"), `wrong_contact` (not the decision
  maker), `manual`. `opt_out` also blocks `reply_send.py`; the others only
  warn there, since someone who declined but then wrote to us still asked a
  question.
- Manage it with `suppress.py` (`--add`, `--list`, `--check`, `--scan`).
  Never keep a do-not-contact list in a file in this repo — the repo is
  public, and the list is other people's personal data.

## Related skills

- `postmark-cold-email` — sending the initial campaign
- `first-follow-up` — forwarding follow-ups to unreplied contacts
- `email-crm` — syncing delivery/open/click/reply status
- `reply-to-replies` — drafting replies to inbound responses
- `conference-crawling` / `edas-crawling` — building the recipient lists these rules protect
- `weekly-stats` — reporting on campaign performance
