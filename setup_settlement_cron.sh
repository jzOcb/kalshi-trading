#!/usr/bin/env bash
# One-time setup: add settlement checker to crontab
# Run with elevated permissions on host

set -euo pipefail

CRON_LINE="0 14 * * * cd /home/clawdbot/clawd && bash kalshi/check_settlements.sh 2>&1 | logger -t kalshi_settle"

# Remove old entry if exists, add new one
(crontab -l 2>/dev/null || true) | grep -v "check_settlements" | { cat; echo "$CRON_LINE"; } | crontab -

echo "✅ Cron job installed:"
crontab -l | grep "check_settlements"
