"""
Polymarket APIs - Unified interface for Polymarket's various APIs.

This package provides a comprehensive interface to Polymarket's APIs including:
- CLOB (Central Limit Order Book) API for trading
- Gamma API for event and market information
- Data API for user information
- Web3 API for blockchain interactions
- WebSocket API for real-time data streams
- GraphQL API for flexible data queries
"""

__version__ = "0.3.2"
__author__ = "Razvan Gheorghe"
__email__ = "razvan@gheorghe.me"

from .clients import (
    AsyncPolymarketGraphQLClient,
    PolymarketClobClient,
    PolymarketDataClient,
    PolymarketGammaClient,
    PolymarketGraphQLClient,
    PolymarketWeb3Client,
    PolymarketWebsocketsClient,
)
from .types.clob_types import MarketOrderArgs, OrderArgs

__all__ = [
    "AsyncPolymarketGraphQLClient",
    "MarketOrderArgs",
    "OrderArgs",
    "PolymarketClobClient",
    "PolymarketDataClient",
    "PolymarketGammaClient",
    "PolymarketGraphQLClient",
    "PolymarketWeb3Client",
    "PolymarketWebsocketsClient",
    "__author__",
    "__email__",
    "__version__",
]
