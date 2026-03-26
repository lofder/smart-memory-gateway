#!/bin/bash
# Engram — Daily Qdrant backup script
# Called by cron. Creates a Qdrant snapshot and keeps last 7 days.

set -euo pipefail

export NO_PROXY=localhost,127.0.0.1
export no_proxy=localhost,127.0.0.1

# Read collection name from config (default: memories)
ENGRAM_DIR="${ENGRAM_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
COLLECTION="${ENGRAM_COLLECTION:-memories}"
QDRANT_HOST="${QDRANT_HOST:-localhost}"
QDRANT_PORT="${QDRANT_PORT:-6333}"
DATA_DIR="${ENGRAM_DATA_DIR:-$HOME/.mem0-gateway/mem0}"
BACKUP_DIR="$DATA_DIR/backups"
LOG_DIR="${ENGRAM_LOG_DIR:-$HOME/.mem0-gateway/logs}"
LOG_FILE="$LOG_DIR/backup.log"

mkdir -p "$BACKUP_DIR" "$LOG_DIR"

RESP=$(curl -s -X POST "http://${QDRANT_HOST}:${QDRANT_PORT}/collections/${COLLECTION}/snapshots")
SNAP_NAME=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['name'])" 2>/dev/null)

if [ -z "$SNAP_NAME" ]; then
    echo "[$(date)] Backup FAILED: $RESP" >> "$LOG_FILE"
    exit 1
fi

# Download snapshot via Qdrant HTTP API
curl -s -o "$BACKUP_DIR/$SNAP_NAME" \
  "http://${QDRANT_HOST}:${QDRANT_PORT}/collections/${COLLECTION}/snapshots/${SNAP_NAME}" 2>/dev/null

# Keep last 7 days
find "$BACKUP_DIR" -name "*.snapshot" -mtime +7 -delete 2>/dev/null

echo "[$(date)] Backup OK: $SNAP_NAME ($(du -sh "$BACKUP_DIR/$SNAP_NAME" 2>/dev/null | cut -f1))" >> "$LOG_FILE"
