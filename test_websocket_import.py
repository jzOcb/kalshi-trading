#!/usr/bin/env python3
"""
Quick test script to verify WebSocket infrastructure modules can be imported
Run this after installing dependencies to verify everything is set up correctly
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test all WebSocket module imports"""
    print("Testing Kalshi WebSocket Infrastructure...")
    print("=" * 60)
    
    try:
        print("\n1. Testing websocket.client...")
        from websocket.client import KalshiWebSocketClient
        print("   ✅ KalshiWebSocketClient imported successfully")
        
        print("\n2. Testing websocket.auth...")
        from websocket.auth import generate_signature, create_auth_headers, load_private_key
        print("   ✅ Authentication functions imported successfully")
        
        print("\n3. Testing websocket.handlers...")
        from websocket.handlers import MessageHandlers
        print("   ✅ MessageHandlers imported successfully")
        
        print("\n4. Testing data.storage...")
        from data.storage import SQLiteStorage
        print("   ✅ SQLiteStorage imported successfully")
        
        print("\n" + "=" * 60)
        print("✅ ALL IMPORTS SUCCESSFUL!")
        print("\nWebSocket infrastructure is ready to use.")
        print("\nNext steps:")
        print("  1. Set up API credentials (see INSTALL-WEBSOCKET.md)")
        print("  2. Try basic example (see WEBSOCKET-README.md)")
        print("  3. Monitor paper trading positions in real-time")
        
        return True
        
    except ImportError as e:
        print(f"\n❌ Import Error: {e}")
        print("\nMissing dependencies. Install with:")
        print("  pip3 install -r requirements-websocket.txt")
        print("\nOr manually:")
        print("  pip3 install websockets aiosqlite cryptography")
        return False
    
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        return False


if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
