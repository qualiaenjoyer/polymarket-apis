from typing import Literal

from gql import Client, gql
from gql.transport.httpx import HTTPXAsyncTransport, HTTPXTransport

from ..utilities.config import GRAPHQL_ENDPOINTS


class PolymarketGraphQLClient:
    """Synchronous GraphQL client for Polymarket subgraphs."""

    def __init__(
        self,
        endpoint_name: Literal[
            "activity_subgraph",
            "fpmm_subgraph",
            "open_interest_subgraph",
            "orderbook_subgraph",
            "pnl_subgraph",
            "positions_subgraph",
            "sports_oracle_subgraph",
            "wallet_subgraph",
        ],
    ) -> None:
        endpoint_url = GRAPHQL_ENDPOINTS[endpoint_name]
        self.transport = HTTPXTransport(url=endpoint_url)
        self.client = Client(
            transport=self.transport, fetch_schema_from_transport=False
        )

    def query(self, query_string: str) -> dict:
        with self.client as session:
            return session.execute(gql(query_string))


class AsyncPolymarketGraphQLClient:
    """Asynchronous GraphQL client for Polymarket subgraphs."""

    def __init__(
        self,
        endpoint_name: Literal[
            "activity_subgraph",
            "fpmm_subgraph",
            "open_interest_subgraph",
            "orderbook_subgraph",
            "pnl_subgraph",
            "positions_subgraph",
            "sports_oracle_subgraph",
            "wallet_subgraph",
        ],
    ) -> None:
        endpoint_url = GRAPHQL_ENDPOINTS[endpoint_name]
        self.transport = HTTPXAsyncTransport(url=endpoint_url)
        self.client = Client(
            transport=self.transport, fetch_schema_from_transport=False
        )

    async def query(self, query_string: str) -> dict:
        async with self.client as session:
            return await session.execute(gql(query_string))
