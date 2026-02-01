#!/bin/bash
# Kalshi Trading System - Installation Script

set -e

echo "🤖 Installing Kalshi Trading System..."
echo ""

# Check dependencies
echo "Checking dependencies..."
if ! command -v python3 &> /dev/null; then
    echo "❌ python3 not found. Please install Python 3."
    exit 1
fi

if ! command -v curl &> /dev/null; then
    echo "❌ curl not found. Please install curl."
    exit 1
fi

echo "✅ python3: $(python3 --version)"
echo "✅ curl: $(curl --version | head -1)"
echo ""

# Create directory structure
echo "Creating directory structure..."
cd "$(dirname "$0")/.."
mkdir -p reports
mkdir -p scripts
mkdir -p examples

echo "✅ Directories created"
echo ""

# Test Python modules
echo "Testing Python modules..."
python3 -c "import json; import urllib.request; print('✅ Standard library OK')" || {
    echo "❌ Python standard library check failed"
    exit 1
}

# Make scripts executable
echo "Making scripts executable..."
chmod +x scripts/*.sh 2>/dev/null || true
chmod +x *.py 2>/dev/null || true
echo "✅ Scripts are executable"
echo ""

# Test API connection
echo "Testing Kalshi API connection..."
if curl -s --max-time 5 "https://api.elections.kalshi.com/trade-api/v2/markets?limit=1" > /dev/null; then
    echo "✅ Kalshi API reachable"
else
    echo "⚠️  Kalshi API unreachable (check network)"
fi
echo ""

# Initialize trades.json if doesn't exist
if [ ! -f trades.json ]; then
    echo "Initializing trades.json..."
    cat > trades.json << 'EOF'
{
  "trades": [],
  "stats": {
    "total": 0,
    "wins": 0,
    "losses": 0,
    "pending": 0
  }
}
EOF
    echo "✅ trades.json created"
else
    echo "✅ trades.json already exists"
fi
echo ""

echo "=================================================="
echo "✅ Installation Complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Test the scanner:"
echo "   cd ~/clawd/kalshi && python3 report_v2.py"
echo ""
echo "2. Set up automation (choose one):"
echo ""
echo "   A) Via Cron (isolated sessions):"
echo '   clawdbot cron add --name "Kalshi scan" \'
echo '     --cron "0 9 * * *" --session isolated \'
echo '     --message "cd ~/clawd/kalshi && python3 report_v2.py" \'
echo '     --channel telegram --deliver'
echo ""
echo "   B) Via Heartbeat (main session):"
echo '   Add to ~/clawd/HEARTBEAT.md:'
echo '   "每天9am: cd ~/clawd/kalshi && python3 report_v2.py"'
echo ""
echo "3. Check paper trading:"
echo "   python3 paper_trading.py"
echo ""
echo "For more info: cat README.md"
echo ""
