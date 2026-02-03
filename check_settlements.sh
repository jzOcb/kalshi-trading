#!/usr/bin/env bash
# Kalshi Paper Trading Settlement Checker - Cron Wrapper
# Runs daily at 14:00 UTC, checks for newly settled markets

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Running settlement check..."

# Use system python3 with requests
python3 kalshi/settlement_checker.py 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "[ERROR] Settlement checker failed with exit code $EXIT_CODE"
fi

# If flag file exists, heartbeat will pick it up
if [ -f /tmp/kalshi_settlement_report.flag ]; then
    echo "[INFO] New settlements found! Report at /tmp/kalshi_settlement_report.txt"
fi

exit $EXIT_CODE
