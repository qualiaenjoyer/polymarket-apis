import json
import logging
from datetime import UTC, datetime
from typing import Literal, Optional
from urllib.parse import urljoin

import httpx
from httpx import HTTPStatusError
from py_order_utils.model import SignedOrder

from ..types.clob_types import (
    ApiCreds,
    BidAsk,
    BookParams,
    ClobMarket,
    CreateOrderOptions,
    DailyEarnedReward,
    MarketOrderArgs,
    Midpoint,
    OpenOrder,
    OrderArgs,
    OrderBookSummary,
    OrderCancelResponse,
    OrderPostResponse,
    OrderType,
    PaginatedResponse,
    PartialCreateOrderOptions,
    PolygonTrade,
    PolymarketRewardItem,
    PostOrdersArgs,
    Price,
    PriceHistory,
    RequestArgs,
    RewardsMarket,
    Spread,
    TickSize,
    TokenBidAskDict,
    TokenValueDict,
)
from ..types.common import EthAddress, Keccak256
from ..utilities.constants import END_CURSOR, POLYGON
from ..utilities.endpoints import (
    ARE_ORDERS_SCORING,
    CANCEL,
    CANCEL_ALL,
    CANCEL_ORDERS,
    CREATE_API_KEY,
    DELETE_API_KEY,
    DERIVE_API_KEY,
    GET_API_KEYS,
    GET_FEE_RATE,
    GET_LAST_TRADE_PRICE,
    GET_LAST_TRADES_PRICES,
    GET_MARKET,
    GET_MARKETS,
    GET_NEG_RISK,
    GET_ORDER_BOOK,
    GET_ORDER_BOOKS,
    GET_PRICES,
    GET_SPREAD,
    GET_SPREADS,
    GET_TICK_SIZE,
    IS_ORDER_SCORING,
    MID_POINT,
    MID_POINTS,
    ORDERS,
    POST_ORDER,
    POST_ORDERS,
    PRICE,
    TIME,
    TRADES,
)
from ..utilities.exceptions import (
    InvalidFeeRateError,
    InvalidPriceError,
    InvalidTickSizeError,
    LiquidityError,
    MissingOrderbookError,
)
from ..utilities.headers import create_level_1_headers, create_level_2_headers
from ..utilities.order_builder.builder import OrderBuilder
from ..utilities.order_builder.helpers import (
    is_tick_size_smaller,
    order_to_json,
    price_valid,
)
from ..utilities.signing.signer import Signer

logger = logging.getLogger(__name__)

class PolymarketClobClient:
    def __init__(
            self,
            private_key: str,
            proxy_address: EthAddress,
            creds: Optional[ApiCreds] = None,
            chain_id: Literal[137, 80002] = POLYGON,
            signature_type: Literal[0, 1, 2] = 1,
            # 0 - EOA wallet, 1 - Proxy wallet, 2 - Gnosis Safe wallet
    ):
        self.proxy_address = proxy_address
        self.client = httpx.Client(http2=True, timeout=30.0)
        self.async_client = httpx.AsyncClient(http2=True, timeout=30.0)
        self.base_url: str = "https://clob.polymarket.com"
        self.signer = Signer(private_key=private_key, chain_id=chain_id)
        self.builder = OrderBuilder(
            signer=self.signer,
            sig_type=signature_type,
            funder=proxy_address,
        )
        self.creds = creds if creds else self.create_or_derive_api_creds()

        # local cache
        self.__tick_sizes = {}
        self.__neg_risk = {}
        self.__fee_rates = {}

    def _build_url(self, endpoint: str) -> str:
        return urljoin(self.base_url, endpoint)

    def get_ok(self) -> str:
        response = self.client.get(self.base_url)
        response.raise_for_status()
        return response.json()

    def create_api_creds(self, nonce: Optional[int] = None) -> ApiCreds:
        headers = create_level_1_headers(self.signer, nonce)
        response = self.client.post(self._build_url(CREATE_API_KEY), headers=headers)
        response.raise_for_status()
        return ApiCreds(**response.json())

    def derive_api_key(self, nonce: Optional[int] = None) -> ApiCreds:
        headers = create_level_1_headers(self.signer, nonce)
        response = self.client.get(self._build_url(DERIVE_API_KEY), headers=headers)
        response.raise_for_status()
        return ApiCreds(**response.json())

    def create_or_derive_api_creds(self, nonce: Optional[int] = None) -> ApiCreds:
        try:
            return self.create_api_creds(nonce)
        except HTTPStatusError:
            return self.derive_api_key(nonce)

    def set_api_creds(self, creds: ApiCreds) -> None:
        self.creds = creds

    def get_api_keys(self) -> dict:
        request_args = RequestArgs(method="GET", request_path=GET_API_KEYS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.client.get(self._build_url(GET_API_KEYS), headers=headers)
        response.raise_for_status()
        return response.json()

    def delete_api_keys(self) -> Literal["OK"]:
        request_args = RequestArgs(method="DELETE", request_path=DELETE_API_KEY)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.client.delete(self._build_url(DELETE_API_KEY), headers=headers)
        response.raise_for_status()
        return response.json()

    def get_utc_time(self) -> datetime:
        # parse server timestamp into utc datetime
        response = self.client.get(self._build_url(TIME))
        response.raise_for_status()
        return datetime.fromtimestamp(response.json(), tz=UTC)

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

    def get_fee_rate_bps(self, token_id: str) -> int:
        if token_id in self.__fee_rates:
            return self.__fee_rates[token_id]

        params = {"token_id": token_id}
        response = self.client.get(self._build_url(GET_FEE_RATE), params=params)
        response.raise_for_status()
        fee_rate = response.json().get("base_fee") or 0
        self.__fee_rates[token_id] = fee_rate

        return fee_rate

    def __resolve_tick_size(
            self, token_id: str, tick_size: TickSize = None,
    ) -> TickSize:
        min_tick_size = self.get_tick_size(token_id)
        if tick_size is not None:
            if is_tick_size_smaller(tick_size, min_tick_size):
                msg = f"invalid tick size ({tick_size!s}), minimum for the market is {min_tick_size!s}"
                raise InvalidTickSizeError(msg)
        else:
            tick_size = min_tick_size
        return tick_size

    def __resolve_fee_rate(
            self, token_id: str, user_fee_rate: Optional[int] = None,
    ) -> int:
        market_fee_rate_bps = self.get_fee_rate_bps(token_id)
        # If both fee rate on the market and the user supplied fee rate are non-zero, validate that they match
        # else return the market fee rate
        if market_fee_rate_bps > 0 and user_fee_rate is not None and user_fee_rate > 0 and user_fee_rate != market_fee_rate_bps:
            msg = f"invalid user provided fee rate: ({user_fee_rate}), fee rate for the market must be {market_fee_rate_bps}"
            raise InvalidFeeRateError(msg)
        return market_fee_rate_bps

    def get_midpoint(self, token_id: str) -> Midpoint:
        """Get the mid-market price for the given token."""
        params = {"token_id": token_id}
        response = self.client.get(self._build_url(MID_POINT), params=params)
        response.raise_for_status()
        return Midpoint(token_id=token_id, value=float(response.json()["mid"]))

    def get_midpoints(self, token_ids: list[str]) -> dict:
        """Get the mid-market prices for a set of tokens."""
        data = [{"token_id": token_id} for token_id in token_ids]
        response = self.client.post(self._build_url(MID_POINTS), json=data)
        response.raise_for_status()
        return TokenValueDict(**response.json()).root

    def get_spread(self, token_id: str) -> Spread:
        """Get the spread for the given token."""
        params = {"token_id": token_id}
        response = self.client.get(self._build_url(GET_SPREAD), params=params)
        response.raise_for_status()
        return Spread(token_id=token_id, value=float(response.json()["mid"]))

    def get_spreads(self, token_ids: list[str]) -> dict:
        """Get the spreads for a set of tokens."""
        data = [{"token_id": token_id} for token_id in token_ids]
        response = self.client.post(self._build_url(GET_SPREADS), json=data)
        response.raise_for_status()
        return TokenValueDict(**response.json()).root

    def get_price(self, token_id: str, side: Literal["BUY", "SELL"]) -> Price:
        """Get the market price for the given token and side."""
        params = {"token_id": token_id, "side": side}
        response = self.client.get(self._build_url(PRICE), params=params)
        response.raise_for_status()
        return Price(**response.json(), token_id=token_id, side=side)

    def get_prices(self, params: list[BookParams]) -> dict[str, BidAsk]:
        """Get the market prices for a set of tokens and sides."""
        data = [{"token_id": param.token_id, "side": param.side} for param in params]
        response = self.client.post(self._build_url(GET_PRICES), json=data)
        response.raise_for_status()
        return TokenBidAskDict(**response.json()).root

    def get_last_trade_price(self, token_id) -> Price:
        """Fetches the last trade price for a token_id."""
        params = {"token_id": token_id}
        response = self.client.get(self._build_url(GET_LAST_TRADE_PRICE), params=params)
        response.raise_for_status()
        return Price(**response.json(), token_id=token_id)

    def get_last_trades_prices(self, token_ids: list[str]) -> list[Price]:
        """Fetches the last trades prices for a set of token ids."""
        body = [{"token_id": token_id} for token_id in token_ids]
        response = self.client.post(self._build_url(GET_LAST_TRADES_PRICES), json=body)
        response.raise_for_status()
        return [Price(**price) for price in response.json()]

    def get_order_book(self, token_id) -> OrderBookSummary:
        """Get the orderbook for the given token."""
        params = {"token_id": token_id}
        response = self.client.get(self._build_url(GET_ORDER_BOOK), params=params)
        response.raise_for_status()
        return OrderBookSummary(**response.json())

    def get_order_books(self, token_ids: list[str]) -> list[OrderBookSummary]:
        """Get the orderbook for a set of tokens."""
        body = [{"token_id": token_id} for token_id in token_ids]
        response = self.client.post(self._build_url(GET_ORDER_BOOKS), json=body)
        response.raise_for_status()
        return [OrderBookSummary(**obs) for obs in response.json()]

    async def get_order_books_async(self, token_ids: list[str]) -> list[OrderBookSummary]:
        """Get the orderbook for a set of tokens asynchronously."""
        body = [{"token_id": token_id} for token_id in token_ids]
        response = await self.async_client.post(self._build_url(GET_ORDER_BOOKS), json=body)
        response.raise_for_status()
        return [OrderBookSummary(**obs) for obs in response.json()]

    def get_market(self, condition_id) -> ClobMarket:
        """Get a ClobMarket by condition_id."""
        response = self.client.get(self._build_url(GET_MARKET + condition_id))
        response.raise_for_status()
        return ClobMarket(**response.json())

    def get_markets(self, next_cursor="MA==")  -> PaginatedResponse[ClobMarket]:
        """Get paginated ClobMarkets."""
        params = {"next_cursor": next_cursor}
        response = self.client.get(self._build_url(GET_MARKETS), params=params)
        response.raise_for_status()
        return PaginatedResponse[ClobMarket](**response.json())

    def get_all_markets(self, next_cursor="MA==") -> list[ClobMarket]:
        """Recursively fetch all ClobMarkets using pagination."""
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
            next_cursor=paginated_response.next_cursor,
        )

        # Combine current page data with data from subsequent pages
        return current_markets + next_page_markets

    def get_recent_history(
            self,
            token_id: str,
            interval: Optional[Literal["1d", "6h", "1h"]] = "1d",
            fidelity: int = 1,  # resolution in minutes
    ) -> PriceHistory:
        """Get the recent price history of a token (up to now) - 1h, 6h, 1d."""
        if fidelity < 1:
            msg = f"invalid filters: minimum 'fidelity' for '{interval}' range is 1"
            raise ValueError(msg)

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
        """Get the price history of a token between selected dates - 1m, 1w, max."""
        min_fidelities = {"1m": 10, "1w": 5, "max": 2}

        if fidelity < min_fidelities[interval]:
            msg = f"invalid filters: minimum 'fidelity' for '{interval}' range is {min_fidelities[interval]}"
            raise ValueError(msg)

        if start_time is None and end_time is None:
            msg = "At least one of 'start_time' or 'end_time' must be provided."
            raise ValueError(msg)

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

    def get_orders(self, order_id: Optional[str] = None, condition_id: Optional[Keccak256] = None, token_id: Optional[str] = None, next_cursor: str ="MA==") -> list[OpenOrder]:
        """Gets your active orders, filtered by order_id, condition_id, token_id."""
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
        """Creates and signs an order."""
        # add resolve_order_options, or similar
        tick_size = self.__resolve_tick_size(
            order_args.token_id,
            options.tick_size if options else None,
        )

        if not price_valid(order_args.price, tick_size):
            msg = f"price ({order_args.price}), min: {tick_size} - max: {1 - float(tick_size)}"
            raise InvalidPriceError(msg)


        neg_risk = (
            options.neg_risk
            if options and options.neg_risk
            else self.get_neg_risk(order_args.token_id)
        )

        # fee rate
        fee_rate_bps = self.__resolve_fee_rate(order_args.token_id, order_args.fee_rate_bps)
        order_args.fee_rate_bps = fee_rate_bps

        return self.builder.create_order(
            order_args,
            CreateOrderOptions(
                tick_size=tick_size,
                neg_risk=neg_risk,
            ),
        )

    def post_order(self, order: SignedOrder, order_type: OrderType = OrderType.GTC) -> Optional[OrderPostResponse]:
        """Posts a SignedOrder."""
        body = order_to_json(order, self.creds.key, order_type)
        headers = create_level_2_headers(
            self.signer,
            self.creds,
            RequestArgs(method="POST", request_path=POST_ORDER, body=body),
        )

        try:
            response = self.client.post(
                self._build_url("/order"),
                headers=headers,
                content=json.dumps(body).encode("utf-8"),
            )
            response.raise_for_status()
            return OrderPostResponse(**response.json())
        except httpx.HTTPStatusError as exc:
            msg = f"Client Error '{exc.response.status_code} {exc.response.reason_phrase}' while posting order"
            logger.warning(msg)
            error_json = exc.response.json()
            print("Details:", error_json["error"])

    def create_and_post_order(self, order_args: OrderArgs, options: Optional[PartialCreateOrderOptions] = None, order_type: OrderType = OrderType.GTC) -> OrderPostResponse:
        """Utility function to create and publish an order."""
        order = self.create_order(order_args, options)
        return self.post_order(order=order, order_type=order_type)

    def post_orders(self, args: list[PostOrdersArgs]):
        """Posts multiple SignedOrders at once."""
        body = [order_to_json(arg.order, self.creds.key, arg.order_type) for arg in args]
        headers = create_level_2_headers(
            self.signer,
            self.creds,
            RequestArgs(method="POST", request_path=POST_ORDERS, body=body),
        )
        try:
            response = self.client.post(
                self._build_url("/orders"),
                headers=headers,
                content=json.dumps(body).encode("utf-8"),
            )
            response.raise_for_status()
            order_responses = []
            for index, item in enumerate(response.json()):
                resp = OrderPostResponse(**item)
                order_responses.append(resp)
                if resp.error_msg:
                    msg = (f"Error posting order in position {index} \n"
                           f"Details: {resp.error_msg}")
                    logger.warning(msg)
        except httpx.HTTPStatusError as exc:
            msg = f"Client Error '{exc.response.status_code} {exc.response.reason_phrase}' while posting order"
            logger.warning(msg)
            error_json = exc.response.json()
            print("Details:", error_json["error"])
        else:
            return order_responses

    def create_and_post_orders(self, args: list[OrderArgs], order_types: list[OrderType]) -> list[OrderPostResponse]:
        """Utility function to create and publish multiple orders at once."""
        return self.post_orders(
            [PostOrdersArgs(order=self.create_order(order_args),
                            order_type=order_type)
             for order_args, order_type in zip(args, order_types, strict=True)],
        )

    def calculate_market_price(self, token_id: str, side: str, amount: float, order_type: OrderType) -> float:
        """Calculates the matching price considering an amount and the current orderbook."""
        book = self.get_order_book(token_id)
        if book is None:
            msg = "Order book is None"
            raise MissingOrderbookError(msg)
        if side == "BUY":
            if book.asks is None:
                msg = "No ask orders available"
                raise LiquidityError(msg)
            return self.builder.calculate_buy_market_price(
                book.asks, amount, order_type,
            )
        if book.bids is None:
            msg = "No bid orders available"
            raise LiquidityError(msg)
        return self.builder.calculate_sell_market_price(
            book.bids, amount, order_type,
        )

    def create_market_order(self, order_args: MarketOrderArgs, options: Optional[PartialCreateOrderOptions] = None):
        """Creates and signs a market order."""
        tick_size = self.__resolve_tick_size(
            order_args.token_id,
            options.tick_size if options else None,
        )

        if order_args.price is None or order_args.price <= 0:
            order_args.price = self.calculate_market_price(
                order_args.token_id,
                order_args.side,
                order_args.amount,
                order_args.order_type,
            )

        if not price_valid(order_args.price, tick_size):
            msg = f"price ({order_args.price}), min: {tick_size} - max: {1 - float(tick_size)}"
            raise InvalidPriceError(msg)

        neg_risk = (
            options.neg_risk
            if options and options.neg_risk
            else self.get_neg_risk(order_args.token_id)
        )

        # fee rate
        fee_rate_bps = self.__resolve_fee_rate(order_args.token_id, order_args.fee_rate_bps)
        order_args.fee_rate_bps = fee_rate_bps

        return self.builder.create_market_order(
            order_args,
            CreateOrderOptions(
                tick_size=tick_size,
                neg_risk=neg_risk,
            ),
        )

    def create_and_post_market_order(
            self,
            order_args: MarketOrderArgs,
            options: Optional[PartialCreateOrderOptions] = None,
            order_type: OrderType = OrderType.FOK,
    ) -> OrderPostResponse:
        """Utility function to create and publish a market order."""
        order = self.create_market_order(order_args, options)
        return self.post_order(order=order, order_type=order_type)

    def cancel_order(self, order_id: Keccak256) -> OrderCancelResponse:
        """Cancels an order."""
        body = {"orderID": order_id}

        request_args = RequestArgs(method="DELETE", request_path=CANCEL, body=body)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.client.request("DELETE", self._build_url(CANCEL), headers=headers, data=json.dumps(body).encode("utf-8"))
        response.raise_for_status()
        return OrderCancelResponse(**response.json())

    def cancel_orders(self, order_ids: list[Keccak256]) -> OrderCancelResponse:
        """Cancels orders."""
        body = order_ids

        request_args = RequestArgs(
            method="DELETE", request_path=CANCEL_ORDERS, body=body,
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.client.request("DELETE", self._build_url(CANCEL_ORDERS), headers=headers, data=json.dumps(body).encode("utf-8"))
        response.raise_for_status()
        return OrderCancelResponse(**response.json())

    def cancel_all(self) -> OrderCancelResponse:
        """Cancels all available orders for the user."""
        request_args = RequestArgs(method="DELETE", request_path=CANCEL_ALL)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.client.delete(self._build_url(CANCEL_ALL), headers=headers)
        response.raise_for_status()
        return OrderCancelResponse(**response.json())

    def is_order_scoring(self, order_id: Keccak256) -> bool:
        """Check if the order is currently scoring."""
        request_args = RequestArgs(method="GET", request_path=IS_ORDER_SCORING)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.client.get(self._build_url(IS_ORDER_SCORING), headers=headers, params={"order_id": order_id})
        response.raise_for_status()
        return response.json()["scoring"]

    def are_orders_scoring(self, order_ids: list[Keccak256]) -> dict[Keccak256, bool]:
        """Check if the orders are currently scoring."""
        body = order_ids
        request_args = RequestArgs(
            method="POST", request_path=ARE_ORDERS_SCORING, body=body,
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        headers["Content-Type"] = "application/json"

        response = self.client.post(self._build_url(ARE_ORDERS_SCORING), headers=headers, json=body)
        response.raise_for_status()
        return response.json()

    def get_rewards_market(self, condition_id: Keccak256) -> RewardsMarket:
        """
        Get the RewardsMarket for a given market (condition_id).

        - metadata, tokens, max_spread, min_size, rewards_config, market_competitiveness.
        """
        request_args = RequestArgs(method="GET", request_path="/rewards/markets/")
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.client.get(self._build_url("/rewards/markets/" + condition_id), headers=headers)
        response.raise_for_status()
        return next(RewardsMarket(**market) for market in response.json()["data"])

    def get_trades(
            self,
            condition_id: Optional[Keccak256] = None,
            token_id: Optional[str] = None,
            trade_id: Optional[str] = None,
            before: Optional[datetime] = None,
            after: Optional[datetime] = None,
            maker_address: Optional[int] = None,
            next_cursor="MA==") -> list[PolygonTrade]:
        """Fetches the trade history for a user."""
        params = {}
        if condition_id:
            params["market"] = condition_id
        if token_id:
            params["asset_id"] = token_id
        if trade_id:
            params["id"] = trade_id
        if before:
            params["before"] = int(before.replace(microsecond=0).timestamp())
        if after:
            params["after"] = int(after.replace(microsecond=0).timestamp())
        if maker_address:
            params["maker_address"] = maker_address

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

    def get_total_rewards(self, date: Optional[datetime] = None) -> DailyEarnedReward:
        """Get the total rewards earned on a given date (seems to only hold the 6 most recent data points)."""
        if date is None:
            date = datetime.now(UTC)
        params = {
            "authenticationType": "magic",
            "date": f"{date.strftime("%Y-%m-%d")}",
        }

        request_args = RequestArgs(method="GET", request_path="/rewards/user/total")
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        params["l2Headers"] = json.dumps(headers)

        response = self.client.get("https://polymarket.com/api/rewards/totalEarnings", params=params)
        response.raise_for_status()
        if response.json():
            return DailyEarnedReward(**response.json()[0])
        return DailyEarnedReward(
            date=date,
            asset_address="0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
            maker_address=self.proxy_address,
            earnings=0.0,
            asset_rate=0.0,
        )

    def get_reward_markets(
            self,
            sort_by: Optional[Literal["market", "max_spread", "min_size", "rate_per_day", "spread", "price", "earnings", "earning_percentage"]] = "market",
            sort_direction: Optional[Literal["ASC", "DESC"]] = None,
            query: Optional[str] = None,
            show_favorites: bool = False,
    ) -> list[PolymarketRewardItem]:
        """
        Get all polymarket.com/rewards items, sorted by different criteria.

         - market start date ("market") - TODO confirm this
         - max spread for rewards in usdc
         - min size for rewards in shares
         - reward rate per day in usdc
         - current spread of a market
         - current price of a market
         - your daily earnings on a market - only need auth for these last two
         - your current earning percentage on a market.
        """
        results = []
        desc = {"ASC": False, "DESC": True}
        params = {
            "authenticationType": "magic",
            "showFavorites": show_favorites,
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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()
