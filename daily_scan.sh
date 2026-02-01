#!/bin/bash
# Daily Kalshi scan and report
# Run this via cron or heartbeat

cd /workspace/kalshi || exit 1

echo "🤖 Daily Kalshi Scan - $(date -u +"%Y-%m-%d %H:%M UTC")"
echo "========================================================================"

# Run the full scan
python3 report_v2.py > /tmp/kalshi_daily_report.txt 2>&1

# Display results
cat /tmp/kalshi_daily_report.txt

# Save to dated file
REPORT_DIR="./reports"
mkdir -p "$REPORT_DIR"
REPORT_FILE="$REPORT_DIR/report-$(date -u +%Y-%m-%d).txt"
cp /tmp/kalshi_daily_report.txt "$REPORT_FILE"

echo ""
echo "📁 Report saved to: $REPORT_FILE"
echo "✅ Scan complete"
