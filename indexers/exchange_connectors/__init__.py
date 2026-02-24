"""
Exchange API Connectors for NearTax
Supports: Coinbase, Crypto.com, Kraken
"""

from .coinbase import CoinbaseConnector
from .cryptocom import CryptoComConnector
from .kraken import KrakenConnector

__all__ = ['CoinbaseConnector', 'CryptoComConnector', 'KrakenConnector']
