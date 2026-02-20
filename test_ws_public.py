#!/usr/bin/env python3
"""
Test Kalshi WebSocket public channel connection
Connects to prod WS, subscribes to ticker + trade for Jason's positions
Runs for 30 seconds then reports results
"""

import asyncio
import json
import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, '/Users/openclaw/clawd/kalshi')

from websocket.client import KalshiWebSocketClient

# Jason's position tickers
TICKERS = [
    "KXGDP-26JAN30-T2.5",
    "KXGDP-26JAN30-T5", 
    "KXCPI-26JAN-T0.0"
]

TIMEOUT = 30  # seconds

# Collect results
results = {
    "connected": False,
    "connection_error": None,
    "subscribed": False,
    "subscription_error": None,
    "messages_received": 0,
    "message_types": {},
    "ticker_updates": {},
    "trades": [],
    "errors": [],
    "raw_messages": []
}


async def message_collector(data):
    """Collect all messages for analysis"""
    msg_type = data.get("type", "unknown")
    results["messages_received"] += 1
    results["message_types"][msg_type] = results["message_types"].get(msg_type, 0) + 1
    
    # Keep first 20 raw messages for debugging
    if len(results["raw_messages"]) < 20:
        results["raw_messages"].append(data)
    
    if msg_type == "ticker":
        msg = data.get("msg", {})
        market = msg.get("market_ticker", "unknown")
        results["ticker_updates"][market] = {
            "yes_bid": msg.get("yes_bid"),
            "yes_ask": msg.get("yes_ask"),
            "last_price": msg.get("last_price"),
            "volume": msg.get("volume"),
        }
        logger.info(f"📊 TICKER {market}: bid={msg.get('yes_bid')}¢ ask={msg.get('yes_ask')}¢ last={msg.get('last_price')}¢")
    
    elif msg_type == "trade":
        msg = data.get("msg", {})
        results["trades"].append({
            "market": msg.get("market_ticker"),
            "price": msg.get("yes_price"),
            "count": msg.get("count"),
        })
        logger.info(f"💰 TRADE {msg.get('market_ticker')}: {msg.get('count')} @ {msg.get('yes_price')}¢")
    
    elif msg_type == "error":
        results["errors"].append(data)
        logger.error(f"❌ ERROR: {data}")
    
    else:
        logger.info(f"📨 {msg_type}: {json.dumps(data, indent=2)[:200]}")


async def test_public_ws():
    """Test public WebSocket connection"""
    logger.info("=" * 60)
    logger.info("Kalshi WebSocket Public Channel Test")
    logger.info(f"URL: wss://api.elections.kalshi.com/trade-api/ws/v2")
    logger.info(f"Tickers: {TICKERS}")
    logger.info(f"Timeout: {TIMEOUT}s")
    logger.info("=" * 60)
    
    client = KalshiWebSocketClient(demo=False, auto_reconnect=False)
    
    # Register a catch-all handler approach: override _handle_message
    original_handle = client._handle_message
    async def catch_all_handle(message):
        try:
            data = json.loads(message)
            await message_collector(data)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON: {message[:200]}")
    client._handle_message = catch_all_handle
    
    # Step 1: Connect
    logger.info("\n--- Step 1: Connecting... ---")
    try:
        await client.connect()
        results["connected"] = True
        logger.info("✅ Connected successfully!")
    except Exception as e:
        results["connection_error"] = str(e)
        logger.error(f"❌ Connection failed: {e}")
        return results
    
    # Step 2: Subscribe
    logger.info("\n--- Step 2: Subscribing to ticker + trade... ---")
    try:
        sub_id = await client.subscribe(
            channels=["ticker", "trade"],
            market_tickers=TICKERS
        )
        results["subscribed"] = True
        logger.info(f"✅ Subscription sent (ID: {sub_id})")
    except Exception as e:
        results["subscription_error"] = str(e)
        logger.error(f"❌ Subscription failed: {e}")
        await client.disconnect()
        return results
    
    # Step 3: Listen for messages with timeout
    logger.info(f"\n--- Step 3: Listening for {TIMEOUT}s... ---")
    try:
        async def listen():
            async for message in client.ws:
                await client._handle_message(message)
        
        await asyncio.wait_for(listen(), timeout=TIMEOUT)
    except asyncio.TimeoutError:
        logger.info(f"⏰ Timeout reached ({TIMEOUT}s)")
    except Exception as e:
        logger.error(f"Error during listen: {e}")
        results["errors"].append({"listen_error": str(e)})
    
    # Disconnect
    try:
        await client.disconnect()
    except:
        pass
    
    return results


async def main():
    res = await test_public_ws()
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    print(f"Connected:          {res['connected']}")
    print(f"Connection Error:   {res['connection_error']}")
    print(f"Subscribed:         {res['subscribed']}")
    print(f"Subscription Error: {res['subscription_error']}")
    print(f"Messages Received:  {res['messages_received']}")
    print(f"Message Types:      {res['message_types']}")
    print(f"Ticker Updates:     {json.dumps(res['ticker_updates'], indent=2)}")
    print(f"Trades Count:       {len(res['trades'])}")
    print(f"Errors:             {res['errors']}")
    
    if res['raw_messages']:
        print(f"\nFirst 5 raw messages:")
        for i, msg in enumerate(res['raw_messages'][:5]):
            print(f"  [{i}] {json.dumps(msg)[:200]}")
    
    # Save results
    output_path = "/Users/openclaw/clawd/kalshi/WS-TEST-RESULTS.md"
    with open(output_path, 'w') as f:
        f.write(f"# WebSocket Test Results\n\n")
        f.write(f"**Date:** {datetime.utcnow().isoformat()}Z\n\n")
        f.write(f"## Connection\n")
        f.write(f"- Connected: {res['connected']}\n")
        f.write(f"- Error: {res['connection_error']}\n\n")
        f.write(f"## Subscription\n")
        f.write(f"- Subscribed: {res['subscribed']}\n")
        f.write(f"- Error: {res['subscription_error']}\n\n")
        f.write(f"## Data\n")
        f.write(f"- Messages received: {res['messages_received']}\n")
        f.write(f"- Message types: {res['message_types']}\n")
        f.write(f"- Ticker updates: {len(res['ticker_updates'])}\n")
        f.write(f"- Trades: {len(res['trades'])}\n")
        f.write(f"- Errors: {len(res['errors'])}\n\n")
        
        if res['ticker_updates']:
            f.write(f"## Latest Ticker Data\n```json\n{json.dumps(res['ticker_updates'], indent=2)}\n```\n\n")
        
        if res['errors']:
            f.write(f"## Errors\n```json\n{json.dumps(res['errors'], indent=2)}\n```\n\n")
        
        if res['raw_messages']:
            f.write(f"## Raw Messages (first 10)\n```json\n")
            for msg in res['raw_messages'][:10]:
                f.write(json.dumps(msg) + "\n")
            f.write("```\n")
    
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
