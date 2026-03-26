#!/bin/bash
# Engram — Maintenance wrapper script
# Called by cron. Uses flock to prevent concurrent runs.

set -euo pipefail

ENGRAM_DIR="${ENGRAM_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
DATA_DIR="${ENGRAM_DATA_DIR:-$HOME/.mem0-gateway/mem0}"
LOG_DIR="${ENGRAM_LOG_DIR:-$HOME/.mem0-gateway/logs}"
LOCKFILE="$DATA_DIR/maintenance-shell.lock"

export NO_PROXY=localhost,127.0.0.1
export no_proxy=localhost,127.0.0.1
export ENGRAM_CONFIG="${ENGRAM_CONFIG:-$ENGRAM_DIR/config.yaml}"

# Source env files for API keys
if [ -f "$HOME/.mem0-gateway/.env" ]; then
  set -a
  source "$HOME/.mem0-gateway/.env"
  set +a
fi

MODE="${1:-daily}"
mkdir -p "$LOG_DIR" "$DATA_DIR"

# Shell-level flock — prevents concurrent cron triggers
exec 9>"$LOCKFILE"
flock -n 9 || { echo "[$(date)] SKIP: another maintenance running (shell lock)" >> "$LOG_DIR/maintenance.log"; exit 0; }

echo "[$(date)] Starting $MODE maintenance" >> "$LOG_DIR/maintenance.log"
timeout 7200 python3 "$ENGRAM_DIR/src/maintenance.py" --mode "$MODE" >> "$LOG_DIR/maintenance.log" 2>&1
EXIT_CODE=$?
echo "[$(date)] Finished $MODE maintenance (exit: $EXIT_CODE)" >> "$LOG_DIR/maintenance.log"

# Retry once on failure (but not on timeout, exit code 124)
if [ $EXIT_CODE -ne 0 ] && [ $EXIT_CODE -ne 124 ]; then
    echo "[$(date)] RETRY: $MODE maintenance" >> "$LOG_DIR/maintenance.log"
    timeout 7200 python3 "$ENGRAM_DIR/src/maintenance.py" --mode "$MODE" >> "$LOG_DIR/maintenance.log" 2>&1
fi
