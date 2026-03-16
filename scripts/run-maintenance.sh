#!/bin/bash
# Smart Memory Gateway v3 - Maintenance wrapper
# Paths resolved at install time by setup.sh
NODE_BIN="/usr/local/Cellar/node@22/22.22.0_1/bin"
PYTHON_BIN="/usr/local/Cellar/python@3.14/3.14.3_1/bin"
export PATH="$NODE_BIN:$PYTHON_BIN:/usr/local/bin:$PATH"
export NO_PROXY=localhost,127.0.0.1
export no_proxy=localhost,127.0.0.1
export GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY_HERE"

MODE="${1:-daily}"
SCRIPT_DIR="$HOME/.openclaw/extensions/mem0-mcp"
LOG_DIR="$HOME/.openclaw/logs"
mkdir -p "$LOG_DIR"

echo "[$(date)] Starting $MODE maintenance" >> "$LOG_DIR/maintenance.log"
python3 "$SCRIPT_DIR/maintenance.py" --mode "$MODE" >> "$LOG_DIR/maintenance.log" 2>&1
EXIT_CODE=$?
echo "[$(date)] Finished $MODE maintenance (exit: $EXIT_CODE)" >> "$LOG_DIR/maintenance.log"

if [ $EXIT_CODE -ne 0 ]; then
    echo "[$(date)] RETRY: $MODE maintenance" >> "$LOG_DIR/maintenance.log"
    python3 "$SCRIPT_DIR/maintenance.py" --mode "$MODE" >> "$LOG_DIR/maintenance.log" 2>&1
fi
