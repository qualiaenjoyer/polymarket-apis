from datetime import datetime, timezone, UTC
from typing import Literal, Optional
from urllib.parse import urljoin

import httpx

from ..types.clob_types import (
    ApiCreds,
    RequestArgs,
    TickSize,
    Midpoint,
    Spread,
    TokenValueDict,
    BookParams,
    BidAsk,
    Price,
    TokenBidAskDict,
    OrderBookSummary,
    PriceHistory,
    ClobMarket,
    PaginatedResponse,
)
from ..types.common import EthAddress
from ..utilities.constants import POLYGON
from ..utilities.endpoints import (
    CREATE_API_KEY,
    DELETE_API_KEY,
    DERIVE_API_KEY,
    GET_API_KEYS,
    TIME,
    GET_TICK_SIZE,
    GET_NEG_RISK,
    MID_POINT,
    MID_POINTS,
    GET_SPREAD,
    GET_SPREADS,
    PRICE,
    GET_PRICES,
    GET_LAST_TRADE_PRICE,
    GET_LAST_TRADES_PRICES,
    GET_ORDER_BOOK,
    GET_ORDER_BOOKS,
    GET_MARKET,
    GET_MARKETS,
)
from ..utilities.headers import create_level_1_headers, create_level_2_headers
from ..utilities.order_builder.builder import OrderBuilder
from ..utilities.signing.signer import Signer


class PolymarketClobClient:
    def __init__(
        self,
        private_key: str,
        proxy_address: EthAddress,
        creds: ApiCreds = None,
        chain_id: Literal[137, 80002] = POLYGON,
    ):
        self.client = httpx.Client(http2=True, timeout=30.0)
        self.base_url: str = "https://clob.polymarket.com"
        self.signature_type = 2
        self.signer = Signer(private_key=private_key, chain_id=chain_id)
        self.builder = OrderBuilder(
            signer=self.signer, sig_type=self.signature_type, funder=proxy_address
        )
        self.creds = creds if creds else self.derive_api_key()

        # local cache
        self.__tick_sizes = {}
        self.__neg_risk = {}

    def _build_url(self, endpoint: str) -> str:
        return urljoin(self.base_url, endpoint)

    def get_ok(self):
        response = self.client.get(self.base_url)
        return response.json()

    def derive_api_key(self, nonce: int = None) -> ApiCreds:
        headers = create_level_1_headers(self.signer, nonce)
        response = self.client.get(self._build_url(DERIVE_API_KEY), headers=headers)
        return ApiCreds(**response.json())

    def create_api_creds(self, nonce: int = None) -> ApiCreds:
        headers = create_level_1_headers(self.signer, nonce)
        response = self.client.post(self._build_url(CREATE_API_KEY), headers=headers)
        return ApiCreds(**response.json())

    def create_or_derive_api_creds(self, nonce: int = None) -> ApiCreds:
        try:
            return self.create_api_creds(nonce)
        except:  # noqa: E722
            return self.derive_api_key(nonce)

    def set_api_creds(self, creds: ApiCreds):
        self.creds = creds

    def get_api_keys(self) -> ApiCreds:
        request_args = RequestArgs(method="GET", request_path=GET_API_KEYS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.client.get(self._build_url(GET_API_KEYS), headers=headers)
        return response.json()

    def delete_api_keys(self) -> ApiCreds:
        request_args = RequestArgs(method="DELETE", request_path=DELETE_API_KEY)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.client.delete(self._build_url(DELETE_API_KEY), headers=headers)
        return response.json()

    def get_utc_time(self) -> datetime:
        # parse server timestamp into utc datetime
        response = self.client.get(self._build_url(TIME))
        response.raise_for_status()
        return datetime.fromtimestamp(response.json(), tz=timezone.utc)

    def get_tick_size(self, token_id: str) -> TickSize:
        if token_id in self.__tick_sizes:
            return self.__tick_sizes[token_id]

        params = {"token_id": token_id}
        response = self.client.get(self._build_url(GET_TICK_SIZE), params=params)
        self.__tick_sizes[token_id] = str(response.json()["minimum_tick_size"])

        return self.__tick_sizes[token_id]

    def get_neg_risk(self, token_id: str) -> bool:
        if token_id in self.__neg_risk:
            return self.__neg_risk[token_id]

        params = {"token_id": token_id}
        response = self.client.get(self._build_url(GET_NEG_RISK), params=params)
        self.__neg_risk[token_id] = response.json()["neg_risk"]

        return self.__neg_risk[token_id]

    def __resolve_tick_size(
        self, token_id: str, tick_size: TickSize = None
    ) -> TickSize:
        min_tick_size = self.get_tick_size(token_id)
        if tick_size is not None:
            if is_tick_size_smaller(tick_size, min_tick_size):
                raise Exception(
                    "invalid tick size ("
                    + str(tick_size)
                    + "), minimum for the market is "
                    + str(min_tick_size),
                )
        else:
            tick_size = min_tick_size
        return tick_size

    def get_midpoint(self, token_id: str) -> Midpoint:
        """
        Get the mid-market price for the given token
        """
        params = {"token_id": token_id}
        response = self.client.get(self._build_url(MID_POINT), params=params)
        return Midpoint(token_id=token_id, value=float(response.json()["mid"]))

    def get_midpoints(self, params: list[BookParams]) -> dict:
        """
        Get the mid-market prices for a set of tokens
        """
        data = [{"token_id": param.token_id} for param in params]
        response = self.client.post(self._build_url(MID_POINTS), json=data)
        return TokenValueDict(**response.json()).root

    def get_spread(self, token_id: str) -> Spread:
        """
        Get the spread for the given token
        """
        params = {"token_id": token_id}
        response = self.client.get(self._build_url(GET_SPREAD), params=params)
        return Spread(token_id=token_id, value=float(response.json()["mid"]))

    def get_spreads(self, params: list[BookParams]) -> dict:
        """
        Get the spreads for a set of tokens
        """
        data = [{"token_id": param.token_id} for param in params]
        response = self.client.post(self._build_url(GET_SPREADS), json=data)
        return TokenValueDict(**response.json()).root

    def get_price(self, token_id: str, side: Literal["BUY", "SELL"]) -> Price:
        """
        Get the market price for the given token and side
        """
        params = {"token_id": token_id, "side": side}
        response = self.client.get(self._build_url(PRICE), params=params)
        return Price(**response.json(), token_id=token_id, side=side)

    def get_prices(self, params: list[BookParams]) -> dict[str, BidAsk]:
        """
        Get the market prices for a set of tokens and sides
        """
        data = [{"token_id": param.token_id, "side": param.side} for param in params]
        response = self.client.post(self._build_url(GET_PRICES), json=data)
        return TokenBidAskDict(**response.json()).root

    def get_last_trade_price(self, token_id) -> Price:
        """
        Fetches the last trade price token_id
        """
        params = {"token_id": token_id}
        response = self.client.get(self._build_url(GET_LAST_TRADE_PRICE), params=params)
        return Price(**response.json(), token_id=token_id)

    def get_last_trades_prices(self, params: list[BookParams]) -> list[Price]:
        """
        Fetches the last trades prices for a set of token ids
        """
        body = [{"token_id": param.token_id} for param in params]
        response = self.client.post(self._build_url(GET_LAST_TRADES_PRICES), json=body)
        return [Price(**price) for price in response.json()]

    def get_order_book(self, token_id) -> OrderBookSummary:
        """
        Get the orderbook for the given token
        """
        params = {"token_id": token_id}
        response = self.client.get(self._build_url(GET_ORDER_BOOK), params=params)
        return OrderBookSummary(**response.json())

    def get_order_books(self, params: list[BookParams]):
        """
        Get the orderbook for a set of tokens
        """
        body = [{"token_id": param.token_id} for param in params]
        response = self.client.post(self._build_url(GET_ORDER_BOOKS), json=body)
        return [OrderBookSummary(**obs) for obs in response.json()]

    def get_market(self, condition_id):
        """
        Get a ClobMarket by condition_id
        """
        response = self.client.get(self._build_url(GET_MARKET + condition_id))
        return ClobMarket(**response.json())

    def get_markets(self, next_cursor="MA=="):
        # TODO fix validation at "ODUwMA==" cursor - bad market setup
        """
        Get paginated ClobMarkets
        """
        params = {"next_cursor": next_cursor}
        response = self.client.get(self._build_url(GET_MARKETS), params=params)
        return PaginatedResponse[ClobMarket](**response.json())

    def get_all_markets(self, next_cursor="MA=="):
        """
        Recursively fetch all ClobMarkets using pagination.
        """
        # Base case: Stop recursion if next_cursor indicates the last page
        if next_cursor == "LTE=":
            print("Reached the last page of markets.")
            return []

        # Fetch current page of markets
        paginated_response = self.get_markets(next_cursor=next_cursor)

        # Collect current page data
        current_markets = paginated_response.data

        # Recursively fetch remaining pages
        next_page_markets = self.get_all_markets(
            next_cursor=paginated_response.next_cursor
        )

        # Combine current page data with data from subsequent pages
        return current_markets + next_page_markets

    def get_recent_history(
        self,
        token_id: str,
        interval: Optional[Literal["1d", "6h", "1h"]] = "1d",
        fidelity: Optional[int] = 1,  # resolution in minutes
    ):
        """
        Get the recent price history of a token (up to now) - 1h, 6h, 1d
        """

        if fidelity < 1:
            raise ValueError(
                f"invalid filters: minimum 'fidelity' for '{interval}' range is 1"
            )

        params = {
            "market": token_id,
            "interval": interval,
            "fidelity": fidelity,
        }
        response = self.client.get(self._build_url("/prices-history"), params=params)
        return PriceHistory(**response.json(), token_id=token_id)

    def get_history(
        self,
        token_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        interval: Optional[Literal["max", "1m", "1w"]] = "max",
        fidelity: Optional[int] = 2,  # resolution in minutes
    ):
        """
        Get the price history of a token between selected dates - 1m, 1w, max
        """
        min_fidelities = {"1m": 10, "1w": 5, "max": 2}

        if fidelity < min_fidelities[interval]:
            raise ValueError(
                f"invalid filters: minimum 'fidelity' for '{interval}' range is {min_fidelities[interval]}"
            )

        if start_time is None and end_time is None:
            raise ValueError(
                "At least one of 'start_time' or 'end_time' must be provided."
            )

        # Default values for timestamps if one is not provided

        if start_time is None:
            start_time = datetime(2020, 1, 1, tzinfo=UTC)  # Default start time
        if end_time is None:
            end_time = datetime.now(UTC)  # Default end time

        params = {
            "market": token_id,
            "startTs": int(start_time.timestamp()),
            "endTs": int(end_time.timestamp()),
            "interval": interval,
            "fidelity": fidelity,
        }
        response = self.client.get(self._build_url("/prices-history"), params=params)
        return PriceHistory(**response.json(), token_id=token_id)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()
