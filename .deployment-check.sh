#!/bin/bash
# Kalshi Deployment Verification Script
# Run this after any changes to scanner/trader to verify integration

set -e

echo "🔍 Kalshi Deployment Verification"
echo "=================================="
echo ""

FAILED=0

# Test 1: Hourly scan produces output
echo "Test 1: Hourly scan output..."
bash /home/clawdbot/clawd/kalshi/send_hourly_scan.sh > /dev/null 2>&1
if [ -f /tmp/kalshi_hourly_scan_dm.txt ]; then
    LINES=$(wc -l < /tmp/kalshi_hourly_scan_dm.txt)
    if [ "$LINES" -gt 20 ]; then
        echo "  ✅ Report generated ($LINES lines)"
    else
        echo "  ❌ Report too short ($LINES lines)"
        FAILED=1
    fi
else
    echo "  ❌ No output file generated"
    FAILED=1
fi

# Test 2: Report has required elements
echo "Test 2: Report format..."
if grep -q "Markets:" /tmp/kalshi_hourly_scan_dm.txt 2>/dev/null; then
    echo "  ✅ Markets count present"
else
    echo "  ❌ Missing markets count"
    FAILED=1
fi

if grep -q "https://kalshi.com/" /tmp/kalshi_hourly_scan_dm.txt 2>/dev/null; then
    echo "  ✅ URLs present"
else
    echo "  ❌ Missing URLs"
    FAILED=1
fi

if grep -q "Score:" /tmp/kalshi_hourly_scan_dm.txt 2>/dev/null; then
    echo "  ✅ Scoring present"
else
    echo "  ❌ Missing scoring"
    FAILED=1
fi

# Test 3: Dynamic trader works
echo "Test 3: Dynamic trader..."
cd /home/clawdbot/clawd/kalshi
OUTPUT=$(python3 dynamic_trader.py monitor 2>&1)
if echo "$OUTPUT" | grep -q "MONITORING"; then
    echo "  ✅ Monitor runs"
else
    echo "  ❌ Monitor failed"
    FAILED=1
fi

# Test 4: Paper trade system
echo "Test 4: Paper trade system..."
if [ -f /home/clawdbot/clawd/kalshi/trades.json ]; then
    if python3 -c "import json; json.load(open('/home/clawdbot/clawd/kalshi/trades.json'))" 2>/dev/null; then
        echo "  ✅ Trades file valid"
    else
        echo "  ❌ Trades file corrupted"
        FAILED=1
    fi
else
    echo "  ⚠️ No trades file (may be empty portfolio)"
fi

echo ""
echo "=================================="
if [ $FAILED -eq 0 ]; then
    echo "✅ All tests passed"
    exit 0
else
    echo "❌ Some tests failed"
    exit 1
fi
