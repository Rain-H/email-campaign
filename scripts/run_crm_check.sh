#!/usr/bin/env bash
# Wrapper for scheduled crm_check.py runs via launchd.
#
# Responsibilities:
#   1. cd into the project so crm_check.py finds .env via load_dotenv().
#   2. Append all output (stdout + stderr) to logs/crm_check.log with a
#      timestamped run banner so weekly runs are easy to scan.
#   3. Always run direct (no LAN proxy) — proxy probing was removed since
#      it added a flaky dependency for no benefit once we confirmed direct
#      connectivity works from this machine.

set -uo pipefail

PROJECT_DIR="/Users/yuhan/paperfox growth/email campaign"
PYTHON_BIN="/Users/yuhan/opt/anaconda3/bin/python"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/crm_check.log"

mkdir -p "$LOG_DIR"

log() {
    printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG_FILE"
}

{
    echo
    echo "================================================================"
    log "scheduled crm_check.py run starting"
} >>"$LOG_FILE"

# Proxy disabled — always use direct connection.
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY 2>/dev/null || true
log "proxy disabled — using direct connection"

cd "$PROJECT_DIR" || {
    log "FATAL: cannot cd to $PROJECT_DIR"
    exit 1
}

# Always write Python output directly to the log file (line-buffered via
# PYTHONUNBUFFERED=1, so the log grows in real time — no 'tee' buffering).
# When invoked from an interactive terminal, also start a side `tail -f`
# that mirrors the log to the user's terminal as it's written. launchd
# runs have no tty, so the mirror is skipped automatically.
TAIL_PID=""
if [ -t 1 ]; then
    tail -n 0 -f "$LOG_FILE" &
    TAIL_PID=$!
    trap 'kill "$TAIL_PID" 2>/dev/null' EXIT INT TERM
fi

PYTHONUNBUFFERED=1 "$PYTHON_BIN" crm_check.py >>"$LOG_FILE" 2>&1
status=$?

log "crm_check.py exited with status ${status}"

if [ -n "$TAIL_PID" ]; then
    # Give tail a moment to flush the final lines, then stop it.
    sleep 1
    kill "$TAIL_PID" 2>/dev/null
fi

exit "$status"
