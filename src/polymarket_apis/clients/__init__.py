"""
Client modules for Polymarket APIs.

This module contains all the client classes for interacting with different
Polymarket APIs including CLOB, Data, Gamma, GraphQL, Web3, and WebSocket clients.
"""

from .clob_client import PolymarketClobClient, PolymarketReadOnlyClobClient
from .data_client import PolymarketDataClient
from .gamma_client import PolymarketGammaClient
from .graphql_client import AsyncPolymarketGraphQLClient, PolymarketGraphQLClient
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
