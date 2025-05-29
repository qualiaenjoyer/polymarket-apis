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
            condition_id: Optional[Union[str, list[str]]] = None,
            size_threshold: float = 1.0,
            redeemable: Optional[bool] = None,
            mergeable: Optional[bool] = None,
            title: Optional[str] = None,
            limit: int = 100,
            offset: int = 0,
            sort_by: Literal[
                "TOKENS",
                "CURRENT",
                "INITIAL",
                "CASHPNL",
                "PERCENTPNL",
                "TITLE",
                "RESOLVING",
                "PRICE",
            ] = "TOKENS",
            sort_direction: Literal["ASC", "DESC"] = "DESC",
    ) -> list[Position]:
        params = {
            "user": user,
            "sizeThreshold": size_threshold,
            "limit": min(limit, 500),
            "offset": offset,
        }
        if isinstance(condition_id, str):
            params["market"] = condition_id
        if isinstance(condition_id, list):
            params["market"] = ",".join(condition_id)
        if redeemable is not None:
            params["redeemable"] = redeemable
        if mergeable is not None:
            params["mergeable"] = mergeable
        if title:
            params["title"] = title
        if sort_by:
            params["sortBy"] = sort_by
        if sort_direction:
            params["sortDirection"] = sort_direction

        response = self.client.get(self._build_url("/positions"), params=params)
        response.raise_for_status()
        return [Position(**pos) for pos in response.json()]

    def get_trades(
            self,
            limit: int = 100,
            offset: int = 0,
            taker_only: bool = True,
            filter_type: Optional[Literal["CASH", "TOKENS"]] = None,
            filter_amount: float = None,
            condition_id: Optional[str] = None,
            user: Optional[str] = None,
            side: Optional[Literal["BUY", "SELL"]] = None,
    ) -> list[Trade]:
        params = {
            "limit": min(limit, 500),
            "offset": offset,
            "takerOnly": taker_only,
        }
        if filter_type:
            params["filterType"] = filter_type
        if filter_amount:
            params["filterAmount"] = filter_amount
        if condition_id:
            params["market"] = condition_id
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
            condition_id: Optional[Union[str, list[str]]] = None,
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
            sort_by: Literal["TIMESTAMP", "TOKENS", "CASH"] = "TIMESTAMP",
            sort_direction: Literal["ASC", "DESC"] = "DESC",
    ) -> list[Activity]:
        params = {"user": user, "limit": min(limit, 500), "offset": offset}
        if isinstance(condition_id, str):
            params["market"] = condition_id
        if isinstance(condition_id, list):
            params["market"] = ",".join(condition_id)
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
        if sort_by:
            params["sortBy"] = sort_by
        if sort_direction:
            params["sortDirection"] = sort_direction

        response = self.client.get(self._build_url("/activity"), params=params)
        response.raise_for_status()
        return [Activity(**activity) for activity in response.json()]

    def get_holders(
            self, condition_id: str, limit: int = 20
    ) -> list[HolderResponse]:
        """
        takes in a condition_id and returns a list of at most 20 top holders for each corresponding token_id
        """
        params = {"market": condition_id, "limit": limit}
        response = self.client.get(self._build_url("/holders"), params=params)
        response.raise_for_status()
        return [
            HolderResponse(**holder_data) for holder_data in response.json()
        ]

    def get_value(
            self, user: str, condition_id: Optional[Union[str, list[str]]] = None
    ) -> ValueResponse:
        """
        takes in condition_id as:
        takes in condition_id as:
            - None      --> total value of positions
            - str       --> value of position
            - list[str] --> sum of the values of positions

        returns the current value of the user's position in a set of markets (condition_isds)
        """
        params = {"user": user}
        if isinstance(condition_id, str):
            params["market"] = condition_id
        if isinstance(condition_id, list):
            params["market"] = ",".join(condition_id)

        response = self.client.get(self._build_url("/value"), params=params)
        response.raise_for_status()
        return ValueResponse(**response.json()[0])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()
