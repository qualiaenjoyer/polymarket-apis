
from typing import Literal, Optional
from urllib.parse import urljoin
from datetime import datetime, timezone, UTC


import json

import httpx
from py_order_utils.model import SignedOrder

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
    RewardsMarket,
    PaginatedResponse,
    PolygonTrade,
    OpenOrder,
    PolymarketRewardItem,
    DailyEarnedReward,
    TimeseriesPoint,
    CreateOrderOptions,
    PartialCreateOrderOptions,
    OrderArgs,
    UserProfit,
    OrderType,
    OrderCancelResponse,
    OrderPostResponse,
)
from ..types.common import EthAddress, Keccak256
from ..utilities.constants import POLYGON, END_CURSOR
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
    ORDERS,
    IS_ORDER_SCORING,
    ARE_ORDERS_SCORING,
    TRADES,
    POST_ORDER,
    CANCEL,
    CANCEL_ORDERS,
    CANCEL_ALL,
    CANCEL_MARKET_ORDERS,
)
from ..utilities.headers import create_level_1_headers, create_level_2_headers
from ..utilities.order_builder.builder import OrderBuilder
from ..utilities.order_builder.helpers import (
    is_tick_size_smaller,
    price_valid,
    order_to_json,
)
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
        self.async_client = httpx.AsyncClient(http2=True, timeout=30.0)
        self.base_url: str = "https://clob.polymarket.com"
        self.signature_type = 2
        self.signer = Signer(private_key=private_key, chain_id=chain_id)
        self.builder = OrderBuilder(
            signer=self.signer,
            sig_type=1,
            funder=proxy_address,
        )
        self.creds = creds if creds else self.derive_api_key()

        # local cache
        self.__tick_sizes = {}
        self.__neg_risk = {}

    def _build_url(self, endpoint: str) -> str:
        return urljoin(self.base_url, endpoint)

    def get_ok(self) -> str:
        response = self.client.get(self.base_url)
        response.raise_for_status()
        return response.json()

    def derive_api_key(self, nonce: int = None) -> ApiCreds:
        headers = create_level_1_headers(self.signer, nonce)
        response = self.client.get(self._build_url(DERIVE_API_KEY), headers=headers)
        response.raise_for_status()
        return ApiCreds(**response.json())

    def create_api_creds(self, nonce: int = None) -> ApiCreds:
        headers = create_level_1_headers(self.signer, nonce)
        response = self.client.post(self._build_url(CREATE_API_KEY), headers=headers)
        response.raise_for_status()
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
        response.raise_for_status()
        return response.json()

    def delete_api_keys(self) -> ApiCreds:
        request_args = RequestArgs(method="DELETE", request_path=DELETE_API_KEY)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.client.delete(self._build_url(DELETE_API_KEY), headers=headers)
        response.raise_for_status()
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
        response.raise_for_status()
        self.__tick_sizes[token_id] = str(response.json()["minimum_tick_size"])

        return self.__tick_sizes[token_id]

    def get_neg_risk(self, token_id: str) -> bool:
        if token_id in self.__neg_risk:
            return self.__neg_risk[token_id]

        params = {"token_id": token_id}
        response = self.client.get(self._build_url(GET_NEG_RISK), params=params)
        response.raise_for_status()
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
        response.raise_for_status()
        return Midpoint(token_id=token_id, value=float(response.json()["mid"]))

    def get_midpoints(self, token_ids: list[str]) -> dict:
        """
        Get the mid-market prices for a set of tokens
        """
        data = [{"token_id": token_id} for token_id in token_ids]
        response = self.client.post(self._build_url(MID_POINTS), json=data)
        response.raise_for_status()
        return TokenValueDict(**response.json()).root

    def get_spread(self, token_id: str) -> Spread:
        """
        Get the spread for the given token
        """
        params = {"token_id": token_id}
        response = self.client.get(self._build_url(GET_SPREAD), params=params)
        response.raise_for_status()
        return Spread(token_id=token_id, value=float(response.json()["mid"]))

    def get_spreads(self, token_ids: list[str]) -> dict:
        """
        Get the spreads for a set of tokens
        """
        data = [{"token_id": token_id} for token_id in token_ids]
        response = self.client.post(self._build_url(GET_SPREADS), json=data)
        response.raise_for_status()
        return TokenValueDict(**response.json()).root

    def get_price(self, token_id: str, side: Literal["BUY", "SELL"]) -> Price:
        """
        Get the market price for the given token and side
        """
        params = {"token_id": token_id, "side": side}
        response = self.client.get(self._build_url(PRICE), params=params)
        response.raise_for_status()
        return Price(**response.json(), token_id=token_id, side=side)

    def get_prices(self, params: list[BookParams]) -> dict[str, BidAsk]:
        """
        Get the market prices for a set of tokens and sides
        """
        data = [{"token_id": param.token_id, "side": param.side} for param in params]
        response = self.client.post(self._build_url(GET_PRICES), json=data)
        response.raise_for_status()
        return TokenBidAskDict(**response.json()).root

    def get_last_trade_price(self, token_id) -> Price:
        """
        Fetches the last trade price token_id
        """
        params = {"token_id": token_id}
        response = self.client.get(self._build_url(GET_LAST_TRADE_PRICE), params=params)
        response.raise_for_status()
        return Price(**response.json(), token_id=token_id)

    def get_last_trades_prices(self, token_ids: list[str]) -> list[Price]:
        """
        Fetches the last trades prices for a set of token ids
        """
        body = [{"token_id": token_id} for token_id in token_ids]
        response = self.client.post(self._build_url(GET_LAST_TRADES_PRICES), json=body)
        response.raise_for_status()
        return [Price(**price) for price in response.json()]

    def get_order_book(self, token_id) -> OrderBookSummary:
        """
        Get the orderbook for the given token
        """
        params = {"token_id": token_id}
        response = self.client.get(self._build_url(GET_ORDER_BOOK), params=params)
        response.raise_for_status()
        return OrderBookSummary(**response.json())

    def get_order_books(self, token_ids: list[str]) -> list[OrderBookSummary]:
        """
        Get the orderbook for a set of tokens
        """
        body = [{"token_id": token_id} for token_id in token_ids]
        response = self.client.post(self._build_url(GET_ORDER_BOOKS), json=body)
        response.raise_for_status()
        return [OrderBookSummary(**obs) for obs in response.json()]

    async def get_order_books_async(self, token_ids: list[str]) -> list[OrderBookSummary]:
        """
        Get the orderbook for a set of tokens asynchronously
        """
        body = [{"token_id": token_id} for token_id in token_ids]
        response = await self.async_client.post(self._build_url(GET_ORDER_BOOKS), json=body)
        response.raise_for_status()
        return [OrderBookSummary(**obs) for obs in response.json()]

    def get_market(self, condition_id) -> ClobMarket:
        """
        Get a ClobMarket by condition_id
        """
        response = self.client.get(self._build_url(GET_MARKET + condition_id))
        response.raise_for_status()
        return ClobMarket(**response.json())
    def get_markets(self, next_cursor="MA==")  -> PaginatedResponse[ClobMarket]:
        # TODO fix validation at "ODUwMA==" cursor - bad market setup
        """
        Get paginated ClobMarkets
        """
        params = {"next_cursor": next_cursor}
        response = self.client.get(self._build_url(GET_MARKETS), params=params)
        response.raise_for_status()
        return PaginatedResponse[ClobMarket](**response.json())

    def get_all_markets(self, next_cursor="MA==") -> list[ClobMarket]:
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
    ) -> PriceHistory:
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
        response.raise_for_status()
        return PriceHistory(**response.json(), token_id=token_id)

    def get_history(
            self,
            token_id: str,
            start_time: Optional[datetime] = None,
            end_time: Optional[datetime] = None,
            interval: Optional[Literal["max", "1m", "1w"]] = "max",
            fidelity: Optional[int] = 2,  # resolution in minutes
    ) -> PriceHistory:
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
        response.raise_for_status()
        return PriceHistory(**response.json(), token_id=token_id)






    def get_orders(self, order_id: str = None, condition_id: Keccak256 = None, token_id: str = None, next_cursor: str ="MA==") -> list[OpenOrder]:
        """
        Gets orders for the API key, optionally filtered by order_id or a combination , condition_id, token_id
        """
        params = {}
        if order_id:
            params["id"] = order_id
        if condition_id:
            params["market"] = condition_id
        if token_id:
            params["asset_id"] = token_id

        request_args = RequestArgs(method="GET", request_path=ORDERS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        results = []
        next_cursor = next_cursor if next_cursor is not None else "MA=="
        while next_cursor != END_CURSOR:
            params["next_cursor"] = next_cursor
            response = self.client.get(self._build_url(ORDERS), headers=headers, params=params)
            response.raise_for_status()
            next_cursor = response.json()["next_cursor"]
            results += [OpenOrder(**order) for order in response.json()["data"]]

        return results

    def create_order(self, order_args: OrderArgs, options: Optional[PartialCreateOrderOptions] = None) -> SignedOrder:
        """
        Creates and signs an order
        """

        # add resolve_order_options, or similar
        tick_size = self.__resolve_tick_size(
            order_args.token_id,
            options.tick_size if options else None,
        )

        if not price_valid(order_args.price, tick_size):
            raise Exception(
                "price ("
                + str(order_args.price)
                + "), min: "
                + str(tick_size)
                + " - max: "
                + str(1 - float(tick_size))
            )

        neg_risk = (
            options.neg_risk
            if options and options.neg_risk
            else self.get_neg_risk(order_args.token_id)
        )

        return self.builder.create_order(
            order_args,
            CreateOrderOptions(
                tick_size=tick_size,
                neg_risk=neg_risk,
            ),
        )

    def post_order(self, order, order_type: Literal["GTC", "FOK", "GTD"] = OrderType.GTC) -> OrderPostResponse:
        # TODO figure out order types - problem with enum serialization
        """"
        Posts the order
        """
        body = order_to_json(order, self.creds.api_key, order_type)
        headers = create_level_2_headers(
            self.signer,
            self.creds,
            RequestArgs(method="POST", request_path=POST_ORDER, body=body),
        )

        response = self.client.post(self._build_url(POST_ORDER), headers=headers, content=json.dumps(body).encode('utf-8'))
        response.raise_for_status()
        return OrderPostResponse(**response.json())

    def create_and_post_order(self, order_args: OrderArgs, options: PartialCreateOrderOptions = None, order_type: OrderType = OrderType.GTC) -> OrderPostResponse:
        """
        Utility function to create and publish an order
        """
        ord = self.create_order(order_args, options)
        return self.post_order(order=ord, order_type=order_type)

    def cancel_order(self, order_id: Keccak256) -> OrderCancelResponse:
        """
        Cancels an order
        """
        body = {"orderID": order_id}

        request_args = RequestArgs(method="DELETE", request_path=CANCEL, body=body)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.client.request("DELETE", self._build_url(CANCEL), headers=headers, data=json.dumps(body).encode('utf-8'))
        response.raise_for_status()
        return OrderCancelResponse(**response.json())

    def cancel_orders(self, order_ids: list[Keccak256]) -> OrderCancelResponse:
        """
        Cancels orders
        """
        body = order_ids

        request_args = RequestArgs(
            method="DELETE", request_path=CANCEL_ORDERS, body=body
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.client.request("DELETE", self._build_url(CANCEL_ORDERS), headers=headers, data=json.dumps(body).encode('utf-8'))
        response.raise_for_status()
        return OrderCancelResponse(**response.json())

    def cancel_all(self) -> OrderCancelResponse:
        """
        Cancels all available orders for the user
        """
        request_args = RequestArgs(method="DELETE", request_path=CANCEL_ALL)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.client.delete(self._build_url(CANCEL_ALL), headers=headers)
        response.raise_for_status()
        return OrderCancelResponse(**response.json())

    def cancel_orders_by(self, condition_id: str = "", token_id: str = ""):
        # TODO figure out how this endpoint works
        """
        Cancels orders for a specific condition_id or token_id
        """
        body = {"market": condition_id, "asset_id": token_id}

        request_args = RequestArgs(
            method="DELETE", request_path=CANCEL_MARKET_ORDERS, body=body
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.client.request("DELETE", self._build_url(CANCEL_MARKET_ORDERS), headers=headers, data=body)
        response.raise_for_status()
        return response.json()

    def is_order_scoring(self, order_id: Keccak256) -> bool:
        """
        Check if the order is currently scoring
        """
        request_args = RequestArgs(method="GET", request_path=IS_ORDER_SCORING)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.client.get(self._build_url(IS_ORDER_SCORING), headers=headers, params={"order_id": order_id})
        response.raise_for_status()
        return response.json()["scoring"]

    def are_orders_scoring(self, order_ids: list[Keccak256]) -> dict[Keccak256, bool]:
        """
        Check if the orders are currently scoring
        """
        body = order_ids
        request_args = RequestArgs(
            method="POST", request_path=ARE_ORDERS_SCORING, body=body
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        headers["Content-Type"] = "application/json"

        response = self.client.post(self._build_url(ARE_ORDERS_SCORING), headers=headers, json=body)
        response.raise_for_status()
        return response.json()

    def get_rewards_market(self, condition_id: Keccak256):
        """
        Get the RewardsMarket for a given market (condition_id)
        - metadata, tokens, max_spread, min_size, rewards_config, market_competitiveness
        """
        request_args = RequestArgs(method="GET", request_path="/rewards/markets/")
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.client.get(self._build_url("/rewards/markets/" + condition_id), headers=headers)
        response.raise_for_status()
        return [RewardsMarket(**market) for market in response.json()["data"]][0]

    def get_trades(
            self,
            condition_id: Optional[Keccak256] = None,
            token_id: Optional[str] = None,
            before: Optional[datetime] = None,
            after: Optional[datetime] = None,
            maker_address: Optional[int] = None,
            id: Optional[str] = None,
            next_cursor="MA==") -> list[PolygonTrade]:
        """
        Fetches the trade history for a user
        """
        params = {}
        if condition_id:
            params["market"] = condition_id
        if token_id:
            params["asset_id"] = token_id
        if before:
            params["before"] = int(before.replace(microsecond=0).timestamp())
        if after:
            params["after"] = int(after.replace(microsecond=0).timestamp())
        if maker_address:
            params["maker_address"] = maker_address
        if id:
            params["id"] = id


        request_args = RequestArgs(method="GET", request_path=TRADES)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        results = []
        next_cursor = next_cursor if next_cursor is not None else "MA=="
        while next_cursor != END_CURSOR:
            params["next_cursor"] = next_cursor
            response =  self.client.get(self._build_url(TRADES), headers=headers, params=params)
            response.raise_for_status()
            next_cursor = response.json()["next_cursor"]
            results += [PolygonTrade(**trade) for trade in response.json()["data"]]

        return results

    def get_total_rewards(self, date: datetime = datetime.now(UTC)) -> float:
        """
        Get the total rewards earned on a given date (seems to only hold the 6 most recent data points)
        """

        params = {
            "authenticationType": "magic",
            "date": f"{date.strftime("%Y-%m-%d")}"
        }

        request_args = RequestArgs(method="GET", request_path="/rewards/user/total")
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        params["l2Headers"] = json.dumps(headers)

        response = self.client.get("https://polymarket.com/api/rewards/totalEarnings", params=params)
        response.raise_for_status()
        return DailyEarnedReward(**response.json()[0])

    def get_reward_markets(
            self,
            sort_by: Optional[Literal["market", "max_spread", "min_size", "rate_per_day", "spread", "price", "earnings", "earning_percentage"]] = "market",
            sort_direction: Optional[Literal["ASC", "DESC"]] = None,
            query: Optional[str] = None,
            show_favorites: bool = False,
    ) -> list[PolymarketRewardItem]:
        """
        Get all polymarket.com/rewards items, sorted by:
         - market start date ("market") - TODO confirm this
         - max spread for rewards in usdc
         - min size for rewards in shares
         - reward rate per day in usdc
         - current spread of a market
         - current price of a market
         - your daily earnings on a market - only need auth for these last two
         - your current earning percentage on a market
        """
        results = []
        desc = {"ASC": False, "DESC": True}
        params = {
            "authenticationType": "magic",
            "showFavorites": show_favorites
        }
        if sort_by:
            params["orderBy"] = sort_by
        if query:
            params["query"] = query
            params["desc"] = False
        if sort_direction:
            params["desc"] = desc[sort_direction]

        request_args = RequestArgs(method="GET", request_path="/rewards/user/markets")
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        params["l2Headers"] = json.dumps(headers)

        next_cursor = "MA=="
        while next_cursor != END_CURSOR:
            params["nextCursor"] = next_cursor
            response = self.client.get("https://polymarket.com/api/rewards/markets", params=params)
            # can probably use clob/rewards/user/markets here but haven't figure out auth
            response.raise_for_status()
            next_cursor = response.json()["next_cursor"]
            results += [PolymarketRewardItem(**reward) for reward in response.json()["data"]]

        return results

    # TODO add notification endpoints

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()
