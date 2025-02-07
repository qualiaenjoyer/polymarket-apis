from datetime import datetime
from typing import Literal, Optional, Union
from urllib.parse import urljoin

import httpx

from ..types.data_types import (
    Activity,
    HolderResponse,
    Position,
    Trade,
    ValueResponse,
)


class PolymarketDataClient:
    def __init__(self, base_url: str = "https://data-api.polymarket.com"):
        self.base_url = base_url
        self.client = httpx.Client(http2=True, timeout=30.0)

    def _build_url(self, endpoint: str) -> str:
        return urljoin(self.base_url, endpoint)

    def get_positions(
        self,
        user: str,
        market: Optional[Union[str, list[str]]] = None,
        sizeThreshold: float = 1.0,
        redeemable: Optional[bool] = None,
        mergeable: Optional[bool] = None,
        title: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        sortBy: Literal[
            "TOKENS",
            "CURRENT",
            "INITIAL",
            "CASHPNL",
            "PERCENTPNL",
            "TITLE",
            "RESOLVING",
            "PRICE",
        ] = "TOKENS",
        sortDirection: Literal["ASC", "DESC"] = "DESC",
    ) -> list[Position]:
        params = {
            "user": user,
            "sizeThreshold": sizeThreshold,
            "limit": min(limit, 500),
            "offset": offset,
        }
        if isinstance(market, str):
            params["market"] = market
        if isinstance(market, list):
            params["market"] = ",".join(market)
        if redeemable is not None:
            params["redeemable"] = redeemable
        if mergeable is not None:
            params["mergeable"] = mergeable
        if title:
            params["title"] = title
        if sortBy:
            params["sortBy"] = sortBy
        if sortDirection:
            params["sortDirection"] = sortDirection

        response = self.client.get(self._build_url("/positions"), params=params)
        response.raise_for_status()
        return [Position(**pos) for pos in response.json()]

    def get_trades(
        self,
        limit: int = 100,
        offset: int = 0,
        takerOnly: bool = True,
        filterType: Optional[Literal["CASH", "TOKENS"]] = None,
        filterAmount: float = None,
        market: Optional[str] = None,
        user: Optional[str] = None,
        side: Optional[Literal["BUY", "SELL"]] = None,
    ) -> list[Trade]:
        params = {
            "limit": min(limit, 500),
            "offset": offset,
            "takerOnly": takerOnly,
        }
        if filterType:
            params["filterType"] = filterType
        if filterAmount:
            params["filterAmount"] = filterAmount
        if market:
            params["market"] = market
        if user:
            params["user"] = user
        if side:
            params["side"] = side

        response = self.client.get(self._build_url("/trades"), params=params)
        response.raise_for_status()
        return [Trade(**trade) for trade in response.json()]

    def get_activity(
        self,
        user: str,
        limit: int = 100,
        offset: int = 0,
        market: Optional[Union[str, list[str]]] = None,
        type: Optional[
            Union[
                Literal[
                    "TRADE", "SPLIT", "MERGE", "REDEEM", "REWARD", "CONVERSION"
                ],
                list[
                    Literal[
                        "TRADE",
                        "SPLIT",
                        "MERGE",
                        "REDEEM",
                        "REWARD",
                        "CONVERSION",
                    ]
                ],
            ]
        ] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        side: Optional[Literal["BUY", "SELL"]] = None,
        sortBy: Literal["TIMESTAMP", "TOKENS", "CASH"] = "TIMESTAMP",
        sortDirection: Literal["ASC", "DESC"] = "DESC",
    ) -> list[Activity]:
        params = {"user": user, "limit": min(limit, 500), "offset": offset}
        if market:
            params["market"] = market
        if isinstance(type, str):
            params["type"] = type
        if isinstance(type, list):
            params["type"] = ",".join(type)
        if start:
            params["start"] = int(start.timestamp())
        if end:
            params["end"] = int(end.timestamp())
        if side:
            params["side"] = side
        if sortBy:
            params["sortBy"] = sortBy
        if sortDirection:
            params["sortDirection"] = sortDirection

        response = self.client.get(self._build_url("/activity"), params=params)
        response.raise_for_status()
        return [Activity(**activity) for activity in response.json()]

    def get_holders(
        self, market: str, limit: int = 100
    ) -> list[HolderResponse]:
        """
        returns a list of the top 20 holders for each token corresponding to a market (conditionId)
        """
        params = {"market": market, "limit": limit}
        response = self.client.get(self._build_url("/holders"), params=params)
        response.raise_for_status()
        return [
            HolderResponse(**holder_data) for holder_data in response.json()
        ]

    def get_value(
        self, user: str, market: Optional[Union[str, list[str]]] = None
    ) -> ValueResponse:
        """
        returns the current value of the user's position(s) in a set of markets (conditionIds)
        takes in individual conditionId str, list[str] or None (all)
        """
        params = {"user": user}
        if isinstance(market, str):
            params["market"] = market
        if isinstance(market, list):
            params["market"] = ",".join(market)

        response = self.client.get(self._build_url("/value"), params=params)
        response.raise_for_status()
        return ValueResponse(**response.json()[0])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()
