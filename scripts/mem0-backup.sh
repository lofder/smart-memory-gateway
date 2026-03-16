#!/bin/bash
# Smart Memory Gateway v3 - Daily Qdrant backup
export NO_PROXY=localhost,127.0.0.1
BACKUP_DIR="$HOME/.mem0-gateway/mem0/backups"
LOG_FILE="$HOME/.mem0-gateway/logs/backup.log"
mkdir -p "$BACKUP_DIR"

RESP=$(curl -s -X POST http://localhost:6333/collections/memories/snapshots)
SNAP_NAME=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['name'])" 2>/dev/null)

if [ -z "$SNAP_NAME" ]; then
    echo "[$(date)] Backup FAILED: $RESP" >> "$LOG_FILE"
    exit 1
fi

SNAP_DIR="$HOME/.mem0-gateway/mem0/qdrant_server_data/snapshots/memories"
cp "$SNAP_DIR/$SNAP_NAME" "$BACKUP_DIR/" 2>/dev/null

# Keep last 7 days
find "$BACKUP_DIR" -name "*.snapshot" -mtime +7 -delete 2>/dev/null

echo "[$(date)] Backup OK: $SNAP_NAME ($(du -sh "$BACKUP_DIR/$SNAP_NAME" 2>/dev/null | cut -f1))" >> "$LOG_FILE"
