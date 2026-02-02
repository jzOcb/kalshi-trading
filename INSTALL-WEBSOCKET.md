# WebSocket Infrastructure Installation Guide

## Prerequisites

- Python 3.8+ (3.9+ recommended)
- pip (Python package manager)
- Internet connection

## Installation Steps

### 1. Install Dependencies

```bash
cd kalshi
pip3 install -r requirements-websocket.txt
```

Or install individually:
```bash
pip3 install websockets aiosqlite cryptography
```

### 2. Verify Installation

```bash
python3 -c "
import websockets
import aiosqlite
import cryptography
print('✅ All dependencies installed successfully!')
"
```

### 3. Test Import

```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from websocket.client import KalshiWebSocketClient
from websocket.handlers import MessageHandlers
from data.storage import SQLiteStorage
print('✅ WebSocket infrastructure ready!')
EOF
```

## Environment Setup (Optional, for authenticated access)

### For Public Channels (Ticker, Trade)

No setup needed! Public channels work without authentication.

### For Private Channels (Orderbook, Fills)

1. **Get API Credentials from Kalshi:**
   - Go to https://kalshi.com/dashboard
   - Navigate to API Keys section
   - Create new API key
   - Download private key (save as `kalshi_private.pem`)

2. **Set Environment Variables:**

```bash
# Add to ~/.bashrc or ~/.zshrc
export KALSHI_API_KEY_ID="your_api_key_id_here"
export KALSHI_PRIVATE_KEY_PATH="/path/to/kalshi_private.pem"
```

3. **Test Authentication:**

```bash
python3 << 'EOF'
import os
from websocket.auth import load_private_key, create_auth_headers

# Load credentials
api_key_id = os.getenv("KALSHI_API_KEY_ID")
key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH", "kalshi_private.pem")

if not api_key_id:
    print("❌ KALSHI_API_KEY_ID not set")
elif not os.path.exists(key_path):
    print(f"❌ Private key not found: {key_path}")
else:
    private_key = load_private_key(key_path)
    headers = create_auth_headers(private_key, api_key_id)
    print("✅ Authentication headers generated successfully!")
    print(f"Key ID: {api_key_id}")
EOF
```

## Quick Test Run

### Test 1: Basic Import (No Network)

```bash
cd kalshi
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from websocket.client import KalshiWebSocketClient
from websocket.handlers import MessageHandlers
from data.storage import SQLiteStorage

print("✅ All modules imported successfully!")
print("WebSocket infrastructure is ready to use.")
EOF
```

### Test 2: Create Storage Database

```bash
cd kalshi
python3 << 'EOF'
import asyncio
import sys
sys.path.insert(0, '.')
from data.storage import SQLiteStorage

async def test():
    storage = SQLiteStorage("data/test.db")
    await storage.connect()
    print("✅ Database created successfully!")
    await storage.close()

asyncio.run(test())
EOF
```

### Test 3: Connection Test (Public Channel)

```bash
cd kalshi
python3 << 'EOF'
import asyncio
import sys
sys.path.insert(0, '.')
from websocket.client import KalshiWebSocketClient

async def test():
    client = KalshiWebSocketClient(demo=False, auto_reconnect=False)
    try:
        await client.connect()
        print("✅ Connected to Kalshi WebSocket!")
        await client.disconnect()
    except Exception as e:
        print(f"❌ Connection failed: {e}")

asyncio.run(test())
EOF
```

## Troubleshooting

### "No module named 'websockets'"

**Solution:**
```bash
pip3 install websockets
# or
python3 -m pip install websockets
```

### "pip: command not found"

**Solution:**
```bash
# Install pip first
python3 -m ensurepip --upgrade
# Then retry installation
python3 -m pip install websockets aiosqlite cryptography
```

### Permission Denied (when installing packages)

**Solution 1: Use --user flag**
```bash
pip3 install --user websockets aiosqlite cryptography
```

**Solution 2: Use virtual environment (recommended)**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-websocket.txt
```

### "cryptography" Installation Fails

**Solution (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install -y python3-dev libssl-dev libffi-dev
pip3 install cryptography
```

**Solution (macOS):**
```bash
brew install openssl
LDFLAGS="-L/usr/local/opt/openssl/lib" pip3 install cryptography
```

### Connection Refused / Timeout

**Check:**
- Internet connection is working
- Firewall allows WebSocket connections (port 443)
- URL is correct:
  - Production: `wss://api.elections.kalshi.com/trade-api/ws/v2`
  - Demo: `wss://demo-api.kalshi.co/trade-api/ws/v2`

### Authentication Failed

**Check:**
- API key ID is correct
- Private key file exists and is readable
- Private key is in PEM format
- System clock is accurate (signature includes timestamp)

## Next Steps

After successful installation:

1. **Read the documentation:** `WEBSOCKET-README.md`
2. **Try basic example:** Monitor ticker for a market
3. **Check examples folder:** `examples/websocket_basic.py`
4. **Integrate with existing system:** Monitor paper trading positions

## Support

If you encounter issues:
- Check Kalshi API status: https://status.kalshi.com
- Review API docs: https://docs.kalshi.com/websockets
- Open issue on GitHub: https://github.com/jzOcb/kalshi-trading/issues
