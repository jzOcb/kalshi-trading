# WebSocket Test Results

**Date:** 2026-02-03T14:14Z  
**Tester:** Subagent (kalshi-websocket task)

## Connection Test

### Result: ❌ FAILED — Authentication Required (HTTP 401)

All WebSocket endpoints require authentication. There are NO public/unauthenticated channels.

### URLs Tested:
| URL | Result |
|-----|--------|
| `wss://api.elections.kalshi.com/trade-api/ws/v2` | HTTP 401 Unauthorized |
| `wss://trading-api.kalshi.com/trade-api/ws/v2` | HTTP 401 Unauthorized |
| `wss://api.kalshi.com/trade-api/ws/v2` | Connection failed (no server) |

### Key Finding:
Despite documentation suggesting public channels (ticker, trade) don't need auth, **Kalshi's WebSocket endpoint itself requires authentication at the connection level** — you can't even open a WebSocket without valid RSA-PSS signed headers.

## Code Fixes Applied

### 1. `websocket/client.py` — Fixed websockets v16 compatibility
The `extra_headers` parameter was renamed to `additional_headers` in websockets v16.0+.
Applied a try/except fallback for both versions.

### Dependencies Status
| Package | Version | Status |
|---------|---------|--------|
| websockets | 16.0 | ✅ Installed |
| aiosqlite | — | ✅ Installed |
| cryptography | — | ✅ Installed |

## What's Needed to Enable WebSocket

1. **Kalshi API Key ID** — from Kalshi dashboard
2. **RSA Private Key** (PEM format) — generated via Kalshi dashboard
3. **Environment variables:**
   ```bash
   KALSHI_API_KEY_ID=<key_id>
   KALSHI_PRIVATE_KEY_PATH=<path_to_pem>
   ```

### How to set up:
1. Jason logs into https://kalshi.com → Settings → API Keys
2. Creates a new API key → downloads private key
3. Save private key as `/home/clawdbot/clawd/kalshi/kalshi_private.pem`
4. Add to `/opt/clawdbot.env`:
   ```
   KALSHI_API_KEY_ID=<the_key_id>
   KALSHI_PRIVATE_KEY_PATH=/home/clawdbot/clawd/kalshi/kalshi_private.pem
   ```

## Fallback: REST API Polling Monitor

Since WebSocket requires auth, created `realtime_monitor.py` using REST API polling as fallback.
This uses the existing REST API infrastructure (already working in the project) to poll prices every 60 seconds.

## Architecture Review

The WebSocket infrastructure code is **well-written and ready to use** once credentials are provided:
- `websocket/client.py` — Clean async client with auto-reconnect ✅
- `websocket/auth.py` — RSA-PSS signing implementation ✅  
- `websocket/handlers.py` — Message handlers with caching ✅
- `data/storage.py` — SQLite persistence layer ✅

Only fix needed was the websockets v16 API change (applied).
