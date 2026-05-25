#!/usr/bin/env bash
# Wrapper for scheduled crm_check.py runs via launchd.
#
# Responsibilities:
#   1. Detect whether the LAN proxy is currently reachable; only export
#      proxy env vars when it is, so the job still works off-network.
#   2. cd into the project so crm_check.py finds .env via load_dotenv().
#   3. Append all output (stdout + stderr) to logs/crm_check.log with a
#      timestamped run banner so weekly runs are easy to scan.

set -uo pipefail

PROJECT_DIR="/Users/yuhan/email campaign"
PYTHON_BIN="/Users/yuhan/opt/anaconda3/bin/python"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/crm_check.log"

PROXY_HOST="192.168.11.123"
PROXY_PORT="16780"
PROXY_PROBE_TIMEOUT="2"

mkdir -p "$LOG_DIR"

log() {
    printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG_FILE"
}

{
    echo
    echo "================================================================"
    log "scheduled crm_check.py run starting"
} >>"$LOG_FILE"

if /usr/bin/nc -z -w "$PROXY_PROBE_TIMEOUT" "$PROXY_HOST" "$PROXY_PORT" >/dev/null 2>&1; then
    export http_proxy="http://${PROXY_HOST}:${PROXY_PORT}"
    export https_proxy="http://${PROXY_HOST}:${PROXY_PORT}"
    export all_proxy="socks5://${PROXY_HOST}:${PROXY_PORT}"
    log "proxy reachable at ${PROXY_HOST}:${PROXY_PORT} — using proxy"
else
    unset http_proxy https_proxy all_proxy 2>/dev/null || true
    log "proxy not reachable — falling back to direct connection"
fi

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
