#!/bin/bash
# Smart Memory Gateway - Maintenance wrapper
# Usage: ./run-maintenance.sh [daily|weekly]

set -euo pipefail

# Resolve project root relative to this script
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Override these via environment or edit here after install
: "${PYTHON_BIN:=$(command -v python3)}"
: "${GOOGLE_API_KEY:?Set GOOGLE_API_KEY before running maintenance}"

export NO_PROXY=localhost,127.0.0.1
export no_proxy=localhost,127.0.0.1
export GOOGLE_API_KEY

MODE="${1:-daily}"
SRC_DIR="$REPO_DIR/src"
LOG_DIR="$REPO_DIR/logs"
mkdir -p "$LOG_DIR"

echo "[$(date)] Starting $MODE maintenance" >> "$LOG_DIR/maintenance.log"
"$PYTHON_BIN" "$SRC_DIR/maintenance.py" --mode "$MODE" >> "$LOG_DIR/maintenance.log" 2>&1
EXIT_CODE=$?
echo "[$(date)] Finished $MODE maintenance (exit: $EXIT_CODE)" >> "$LOG_DIR/maintenance.log"

if [ $EXIT_CODE -ne 0 ]; then
    echo "[$(date)] RETRY: $MODE maintenance" >> "$LOG_DIR/maintenance.log"
    sleep 10
    "$PYTHON_BIN" "$SRC_DIR/maintenance.py" --mode "$MODE" >> "$LOG_DIR/maintenance.log" 2>&1
fi
