"""
Client modules for Polymarket APIs.

This module contains all the client classes for interacting with different
Polymarket APIs including CLOB, Data, Gamma, GraphQL, Web3, and WebSocket clients.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .clob_client import PolymarketClobClient, PolymarketReadOnlyClobClient
    from .data_client import PolymarketDataClient
    from .gamma_client import PolymarketGammaClient
    from .graphql_client import (
        AsyncPolymarketGraphQLClient,
        PolymarketGraphQLClient,
    )
    from .web3_client import PolymarketGaslessWeb3Client, PolymarketWeb3Client
    from .websockets_client import (
        PolymarketWebsocketsClient,
        parse_live_data_event,
        parse_market_event,
        parse_sports_event,
        parse_user_event,
    )

__all__ = [
    "AsyncPolymarketGraphQLClient",
    "PolymarketClobClient",
    "PolymarketDataClient",
    "PolymarketGammaClient",
    "PolymarketGaslessWeb3Client",
    "PolymarketGraphQLClient",
    "PolymarketReadOnlyClobClient",
    "PolymarketWeb3Client",
    "PolymarketWebsocketsClient",
    "parse_live_data_event",
    "parse_market_event",
    "parse_sports_event",
    "parse_user_event",
]

_EXPORT_MAP = {
    "AsyncPolymarketGraphQLClient": ".graphql_client",
    "PolymarketClobClient": ".clob_client",
    "PolymarketDataClient": ".data_client",
    "PolymarketGammaClient": ".gamma_client",
    "PolymarketGaslessWeb3Client": ".web3_client",
    "PolymarketGraphQLClient": ".graphql_client",
    "PolymarketReadOnlyClobClient": ".clob_client",
    "PolymarketWeb3Client": ".web3_client",
    "PolymarketWebsocketsClient": ".websockets_client",
    "parse_live_data_event": ".websockets_client",
    "parse_market_event": ".websockets_client",
    "parse_sports_event": ".websockets_client",
    "parse_user_event": ".websockets_client",
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
