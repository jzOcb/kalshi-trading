#!/bin/bash
# Kalshi Dynamic Trading Alert System
# Monitors positions and sends trading signals to Jason

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Run monitor
OUTPUT=$(python3 dynamic_trader.py monitor 2>&1)

# Check if there are recommendations
if echo "$OUTPUT" | grep -q "TRADING RECOMMENDATIONS"; then
    # Extract recommendations
    RECS=$(echo "$OUTPUT" | sed -n '/🎯/,/===/p')
    
    # Send to Jason via message tool
    clawdbot message send \
        --channel telegram \
        --target 6978208486 \
        --message "🔔 **Kalshi Trading Signal**

$RECS

Run \`cd kalshi && python3 dynamic_trader.py monitor\` for full analysis.

To execute:
\`python3 dynamic_trader.py execute <trade_id> <action> <price>\`"
fi

# Always log
echo "$OUTPUT" >> "$SCRIPT_DIR/dynamic_trading.log"
