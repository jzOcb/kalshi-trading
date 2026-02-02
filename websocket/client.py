"""
Kalshi WebSocket Client
Real-time market data streaming with auto-reconnection
"""

import asyncio
import json
import logging
from typing import Callable, Optional, List, Dict, Any
import websockets
from websockets.exceptions import ConnectionClosed

from .auth import create_auth_headers, load_private_key


logger = logging.getLogger(__name__)


class KalshiWebSocketClient:
    """
    Kalshi WebSocket client with authentication and auto-reconnection
    
    Features:
    - Authenticated and unauthenticated connections
    - Auto-reconnection with exponential backoff
    - Channel subscription management
    - Message routing to handlers
    - Heartbeat/ping-pong keep-alive
    """
    
    # WebSocket URLs
    PROD_WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    DEMO_WS_URL = "wss://demo-api.kalshi.co/trade-api/ws/v2"
    
    def __init__(self, 
                 api_key_id: Optional[str] = None,
                 private_key_path: Optional[str] = None,
                 demo: bool = False,
                 auto_reconnect: bool = True,
                 max_reconnect_delay: int = 60):
        """
        Initialize Kalshi WebSocket client
        
        Args:
            api_key_id: Kalshi API key ID (optional for public channels)
            private_key_path: Path to RSA private key (optional for public channels)
            demo: Use demo environment (default: False)
            auto_reconnect: Enable auto-reconnection (default: True)
            max_reconnect_delay: Maximum reconnection delay in seconds (default: 60)
        """
        self.api_key_id = api_key_id
        self.private_key_path = private_key_path
        self.demo = demo
        self.auto_reconnect = auto_reconnect
        self.max_reconnect_delay = max_reconnect_delay
        
        # WebSocket connection
        self.ws = None
        self.ws_url = self.DEMO_WS_URL if demo else self.PROD_WS_URL
        
        # Connection state
        self.connected = False
        self.authenticated = False
        self.message_id = 1
        self.reconnect_delay = 1  # Start with 1 second
        
        # Subscriptions tracking
        self.subscriptions = {}  # {subscription_id: {channels, market_tickers}}
        
        # Message handlers
        self.handlers = {}  # {message_type: handler_function}
        
        # Private key for authentication
        self.private_key = None
        if private_key_path:
            self.private_key = load_private_key(private_key_path)
            self.authenticated = True
    
    async def connect(self):
        """Establish WebSocket connection with optional authentication"""
        try:
            # Create headers (authenticated or not)
            headers = {}
            if self.authenticated and self.private_key and self.api_key_id:
                headers = create_auth_headers(self.private_key, self.api_key_id)
                logger.info("Connecting with authentication...")
            else:
                logger.info("Connecting without authentication (public channels only)...")
            
            # Connect to WebSocket
            self.ws = await websockets.connect(
                self.ws_url,
                extra_headers=headers,
                ping_interval=20,  # Send ping every 20s
                ping_timeout=10    # Wait 10s for pong
            )
            
            self.connected = True
            self.reconnect_delay = 1  # Reset reconnect delay on success
            logger.info(f"Connected to {self.ws_url}")
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.connected = False
            raise
    
    async def disconnect(self):
        """Close WebSocket connection"""
        if self.ws:
            await self.ws.close()
            self.connected = False
            logger.info("Disconnected from Kalshi WebSocket")
    
    async def subscribe(self, 
                       channels: List[str], 
                       market_tickers: Optional[List[str]] = None) -> int:
        """
        Subscribe to data channels
        
        Args:
            channels: List of channel names (e.g., ["ticker", "orderbook_delta"])
            market_tickers: Optional list of market tickers to filter (e.g., ["KXBTC-26FEB"])
        
        Returns:
            subscription_id: ID of the subscription for tracking
        
        Channel Types:
        - Public: ticker, ticker_v2, trade, market_lifecycle_v2, multivariate
        - Private: orderbook_delta, fill, market_positions, communications, order_group_updates
        """
        subscription_msg = {
            "id": self.message_id,
            "cmd": "subscribe",
            "params": {
                "channels": channels
            }
        }
        
        # Add market filter if specified
        if market_tickers:
            subscription_msg["params"]["market_tickers"] = market_tickers
        
        # Send subscription command
        await self.ws.send(json.dumps(subscription_msg))
        
        # Track subscription
        subscription_id = self.message_id
        self.subscriptions[subscription_id] = {
            "channels": channels,
            "market_tickers": market_tickers
        }
        
        logger.info(f"Subscribed to {channels} (ID: {subscription_id})")
        self.message_id += 1
        
        return subscription_id
    
    async def unsubscribe(self, subscription_id: int):
        """
        Unsubscribe from channels
        
        Args:
            subscription_id: ID returned from subscribe()
        """
        unsubscribe_msg = {
            "id": self.message_id,
            "cmd": "unsubscribe",
            "params": {
                "sids": [subscription_id]
            }
        }
        
        await self.ws.send(json.dumps(unsubscribe_msg))
        
        # Remove from tracking
        if subscription_id in self.subscriptions:
            del self.subscriptions[subscription_id]
        
        logger.info(f"Unsubscribed from subscription {subscription_id}")
        self.message_id += 1
    
    def register_handler(self, message_type: str, handler: Callable):
        """
        Register a message handler for specific message types
        
        Args:
            message_type: Message type (e.g., "ticker", "orderbook_delta", "error")
            handler: Async function to handle messages: async def handler(data: dict)
        """
        self.handlers[message_type] = handler
        logger.debug(f"Registered handler for '{message_type}'")
    
    async def _handle_message(self, message: str):
        """Process incoming WebSocket message"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            # Route to registered handler
            if msg_type in self.handlers:
                await self.handlers[msg_type](data)
            else:
                # Default logging for unhandled messages
                logger.debug(f"Unhandled message type '{msg_type}': {data}")
        
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {message}")
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
    
    async def run(self):
        """
        Main event loop - connect, receive messages, handle reconnections
        
        This is the main entry point. It runs indefinitely and handles:
        - Initial connection
        - Message processing
        - Auto-reconnection on disconnect
        """
        while True:
            try:
                # Connect if not connected
                if not self.connected:
                    await self.connect()
                
                # Listen for messages
                async for message in self.ws:
                    await self._handle_message(message)
            
            except ConnectionClosed as e:
                logger.warning(f"Connection closed: {e}")
                self.connected = False
                
                # Auto-reconnect with exponential backoff
                if self.auto_reconnect:
                    logger.info(f"Reconnecting in {self.reconnect_delay}s...")
                    await asyncio.sleep(self.reconnect_delay)
                    self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
                else:
                    break
            
            except Exception as e:
                logger.error(f"Unexpected error: {e}", exc_info=True)
                self.connected = False
                
                if self.auto_reconnect:
                    await asyncio.sleep(self.reconnect_delay)
                    self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
                else:
                    break
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
