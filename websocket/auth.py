"""
Kalshi WebSocket Authentication
Handles RSA-PSS signing for WebSocket connections
"""

import base64
import time
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding


def generate_signature(private_key, method: str, path: str, timestamp: str) -> str:
    """
    Generate RSA-PSS signature for Kalshi API authentication
    
    Args:
        private_key: RSA private key object
        method: HTTP method (e.g., "GET")
        path: API path (e.g., "/trade-api/ws/v2")
        timestamp: Unix timestamp in milliseconds (as string)
    
    Returns:
        Base64-encoded signature
    """
    # Create message to sign: timestamp + method + path
    message = f"{timestamp}{method}{path}".encode('utf-8')
    
    # Sign using RSA-PSS
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH
        ),
        hashes.SHA256()
    )
    
    # Return base64-encoded signature
    return base64.b64encode(signature).decode('utf-8')


def load_private_key(key_path: str, password: bytes = None):
    """
    Load RSA private key from PEM file
    
    Args:
        key_path: Path to private key file
        password: Optional password for encrypted keys
    
    Returns:
        RSA private key object
    """
    with open(key_path, 'rb') as f:
        private_key = serialization.load_pem_private_key(
            f.read(),
            password=password
        )
    return private_key


def create_auth_headers(private_key, api_key_id: str, method: str = "GET", 
                        path: str = "/trade-api/ws/v2") -> dict:
    """
    Create authentication headers for WebSocket connection
    
    Args:
        private_key: RSA private key object
        api_key_id: Kalshi API key ID
        method: HTTP method (default: "GET")
        path: API path (default: "/trade-api/ws/v2")
    
    Returns:
        Dictionary of authentication headers
    """
    timestamp = str(int(time.time() * 1000))
    signature = generate_signature(private_key, method, path, timestamp)
    
    return {
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
        "Content-Type": "application/json"
    }
