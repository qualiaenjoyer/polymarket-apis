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

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__version__ = "0.5.5"
__author__ = "Razvan Gheorghe"
__email__ = "razvan@gheorghe.me"

if TYPE_CHECKING:
    from .clients import (
        AsyncPolymarketGraphQLClient,
        PolymarketClobClient,
        PolymarketDataClient,
        PolymarketGammaClient,
        PolymarketGaslessWeb3Client,
        PolymarketGraphQLClient,
        PolymarketReadOnlyClobClient,
        PolymarketWeb3Client,
        PolymarketWebsocketsClient,
    )
    from .types.clob_types import (
        ApiCreds,
        MarketOrderArgs,
        OrderArgs,
        OrderType,
    )

__all__ = [
    "ApiCreds",
    "AsyncPolymarketGraphQLClient",
    "MarketOrderArgs",
    "OrderArgs",
    "OrderType",
    "PolymarketClobClient",
    "PolymarketDataClient",
    "PolymarketGammaClient",
    "PolymarketGaslessWeb3Client",
    "PolymarketGraphQLClient",
    "PolymarketReadOnlyClobClient",
    "PolymarketWeb3Client",
    "PolymarketWebsocketsClient",
    "__author__",
    "__email__",
    "__version__",
]

_EXPORT_MAP = {
    "ApiCreds": ".types.clob_types",
    "AsyncPolymarketGraphQLClient": ".clients",
    "MarketOrderArgs": ".types.clob_types",
    "OrderArgs": ".types.clob_types",
    "OrderType": ".types.clob_types",
    "PolymarketClobClient": ".clients",
    "PolymarketDataClient": ".clients",
    "PolymarketGammaClient": ".clients",
    "PolymarketGaslessWeb3Client": ".clients",
    "PolymarketGraphQLClient": ".clients",
    "PolymarketReadOnlyClobClient": ".clients",
    "PolymarketWeb3Client": ".clients",
    "PolymarketWebsocketsClient": ".clients",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MAP.get(name)
    if module_name is None:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)

    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
