"""
Message Handlers for Kalshi WebSocket
Example handlers for different message types
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class MessageHandlers:
    """Collection of message handlers for Kalshi WebSocket messages"""
    
    def __init__(self, storage=None):
        """
        Initialize handlers
        
        Args:
            storage: Optional storage backend for persisting data
        """
        self.storage = storage
        self.ticker_cache = {}  # {market_ticker: latest_ticker_data}
        self.orderbook_cache = {}  # {market_ticker: orderbook_snapshot}
    
    async def handle_subscribed(self, data: Dict[str, Any]):
        """Handle subscription confirmation"""
        logger.info(f"✅ Subscription confirmed: {data}")
    
    async def handle_ticker(self, data: Dict[str, Any]):
        """
        Handle ticker updates (real-time price changes)
        
        Message format:
        {
            "type": "ticker",
            "seq": 12345,
            "msg": {
                "market_ticker": "KXBTC-26FEB",
                "yes_bid": 45,
                "yes_ask": 47,
                "no_bid": 53,
                "no_ask": 55,
                "last_price": 46,
                "volume": 1250,
                "open_interest": 5000
            }
        }
        """
        msg = data.get("msg", {})
        market = msg.get("market_ticker")
        
        # Cache latest ticker
        self.ticker_cache[market] = {
            "timestamp": datetime.utcnow().isoformat(),
            "yes_bid": msg.get("yes_bid"),
            "yes_ask": msg.get("yes_ask"),
            "spread": msg.get("yes_ask", 0) - msg.get("yes_bid", 0),
            "last_price": msg.get("last_price"),
            "volume": msg.get("volume"),
            "open_interest": msg.get("open_interest")
        }
        
        logger.debug(f"📊 {market}: Yes {msg.get('yes_bid')}¢/{msg.get('yes_ask')}¢ " +
                    f"(spread: {self.ticker_cache[market]['spread']}¢)")
        
        # Persist to storage if available
        if self.storage:
            await self.storage.save_ticker(market, self.ticker_cache[market])
    
    async def handle_orderbook_snapshot(self, data: Dict[str, Any]):
        """
        Handle full orderbook snapshot (initial state after subscription)
        
        Message format:
        {
            "type": "orderbook_snapshot",
            "seq": 12345,
            "msg": {
                "market_ticker": "KXBTC-26FEB",
                "yes": [[45, 100], [44, 200]],  # [price, quantity]
                "no": [[55, 150], [56, 100]]
            }
        }
        """
        msg = data.get("msg", {})
        market = msg.get("market_ticker")
        
        # Cache orderbook
        self.orderbook_cache[market] = {
            "timestamp": datetime.utcnow().isoformat(),
            "yes_levels": msg.get("yes", []),
            "no_levels": msg.get("no", []),
            "seq": data.get("seq")
        }
        
        yes_depth = sum(q for p, q in msg.get("yes", []))
        no_depth = sum(q for p, q in msg.get("no", []))
        
        logger.info(f"📖 Orderbook snapshot for {market}: " +
                   f"YES depth={yes_depth}, NO depth={no_depth}")
        
        # Persist to storage
        if self.storage:
            await self.storage.save_orderbook_snapshot(market, self.orderbook_cache[market])
    
    async def handle_orderbook_delta(self, data: Dict[str, Any]):
        """
        Handle incremental orderbook updates
        
        Message format:
        {
            "type": "orderbook_delta",
            "seq": 12346,
            "msg": {
                "market_ticker": "KXBTC-26FEB",
                "price": 46,
                "delta": 50,  # Positive = added, negative = removed
                "side": "yes",
                "client_order_id": "optional-your-order-id"  # Only if you caused this change
            }
        }
        """
        msg = data.get("msg", {})
        market = msg.get("market_ticker")
        price = msg.get("price")
        delta = msg.get("delta")
        side = msg.get("side")
        
        # Check if this was caused by our own order
        caused_by_us = "client_order_id" in msg
        
        logger.debug(f"📝 {market} orderbook delta: {side.upper()} {price}¢ " +
                    f"{'added' if delta > 0 else 'removed'} {abs(delta)} contracts" +
                    (f" (your order: {msg['client_order_id']})" if caused_by_us else ""))
        
        # Update cached orderbook
        if market in self.orderbook_cache:
            levels = self.orderbook_cache[market][f"{side}_levels"]
            # Find and update the price level
            for i, (p, q) in enumerate(levels):
                if p == price:
                    new_qty = q + delta
                    if new_qty <= 0:
                        levels.pop(i)  # Remove level if empty
                    else:
                        levels[i] = [p, new_qty]
                    break
            else:
                # New price level
                if delta > 0:
                    levels.append([price, delta])
                    levels.sort(key=lambda x: x[0], reverse=(side == "yes"))
        
        # Persist to storage
        if self.storage:
            await self.storage.save_orderbook_delta(market, {
                "timestamp": datetime.utcnow().isoformat(),
                "price": price,
                "delta": delta,
                "side": side,
                "seq": data.get("seq"),
                "caused_by_us": caused_by_us
            })
    
    async def handle_trade(self, data: Dict[str, Any]):
        """
        Handle trade executions
        
        Message format:
        {
            "type": "trade",
            "seq": 12347,
            "msg": {
                "market_ticker": "KXBTC-26FEB",
                "yes_price": 46,
                "no_price": 54,
                "count": 100,
                "taker_side": "yes"
            }
        }
        """
        msg = data.get("msg", {})
        market = msg.get("market_ticker")
        
        logger.info(f"💰 Trade: {market} — {msg.get('count')} @ " +
                   f"YES={msg.get('yes_price')}¢ / NO={msg.get('no_price')}¢ " +
                   f"(taker: {msg.get('taker_side')})")
        
        # Persist to storage
        if self.storage:
            await self.storage.save_trade(market, {
                "timestamp": datetime.utcnow().isoformat(),
                "yes_price": msg.get("yes_price"),
                "no_price": msg.get("no_price"),
                "count": msg.get("count"),
                "taker_side": msg.get("taker_side"),
                "seq": data.get("seq")
            })
    
    async def handle_fill(self, data: Dict[str, Any]):
        """
        Handle order fill notifications (private channel, requires auth)
        
        Message format:
        {
            "type": "fill",
            "seq": 12348,
            "msg": {
                "order_id": "abc123",
                "market_ticker": "KXBTC-26FEB",
                "side": "yes",
                "action": "buy",
                "count": 50,
                "yes_price": 46,
                "is_taker": true
            }
        }
        """
        msg = data.get("msg", {})
        
        logger.info(f"🎯 FILL: Order {msg.get('order_id')} — " +
                   f"{msg.get('action').upper()} {msg.get('count')} {msg.get('side')} @ " +
                   f"{msg.get('yes_price')}¢ in {msg.get('market_ticker')}")
        
        # Persist to storage
        if self.storage:
            await self.storage.save_fill(msg)
    
    async def handle_error(self, data: Dict[str, Any]):
        """Handle error messages from server"""
        msg = data.get("msg", {})
        error_code = msg.get("code")
        error_msg = msg.get("msg")
        
        logger.error(f"❌ WebSocket Error {error_code}: {error_msg}")
        logger.error(f"Full error data: {data}")
    
    def get_latest_ticker(self, market_ticker: str) -> Optional[Dict[str, Any]]:
        """Get latest cached ticker for a market"""
        return self.ticker_cache.get(market_ticker)
    
    def get_orderbook(self, market_ticker: str) -> Optional[Dict[str, Any]]:
        """Get latest cached orderbook for a market"""
        return self.orderbook_cache.get(market_ticker)
