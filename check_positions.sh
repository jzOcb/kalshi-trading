#!/usr/bin/env bash
# Kalshi Position Monitor — cron wrapper
# Runs every hour at :30 to check position prices

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/usr/bin/python3"
LOG_FILE="/tmp/kalshi_position_monitor.log"

echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Running position monitor..." >> "$LOG_FILE"

cd "$SCRIPT_DIR"

if $PYTHON "$SCRIPT_DIR/position_monitor.py" >> "$LOG_FILE" 2>&1; then
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Position monitor completed OK" >> "$LOG_FILE"
else
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Position monitor FAILED (exit $?)" >> "$LOG_FILE"
fi

# Keep log manageable
tail -200 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
