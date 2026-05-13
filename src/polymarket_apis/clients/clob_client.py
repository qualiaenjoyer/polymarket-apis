import json
import logging
import random
import time
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any, Literal, Optional, Self, cast
from urllib.parse import urljoin

import httpx
from httpx import HTTPStatusError

from ..types.clob_types import (
    ApiCreds,
    BidAsk,
    BookParams,
    ClobMarket,
    ClobMarketInfo,
    CreateOrderOptions,
    CryptoOutcome,
    DailyEarnedReward,
    FeeInfo,
    MarketIDs,
    MarketOrderArgs,
    MarketRewards,
    Midpoint,
    OpenOrder,
    OrderArgs,
    OrderBookSummary,
    OrderCancelResponse,
    OrderPostResponse,
    OrderType,
    PaginatedResponse,
    PartialCreateOrderOptions,
    PastResultsResponse,
    PolygonTrade,
    PostOrdersArgs,
    Price,
    PriceHistory,
    RequestArgs,
    RewardMarket,
    Spread,
    TickSize,
    TokenBidAskDict,
    TokenValueDict,
)
from ..types.common import EthAddress, Keccak256
from ..utilities._internal_log import (
    emit,
    ensure_trace_id,
    get_logger,
    log_extra,
    reset_trace_id,
)
from ..utilities.constants import END_CURSOR, POLYGON
from ..utilities.endpoints import (
    ARE_ORDERS_SCORING,
    CANCEL,
    CANCEL_ALL,
    CANCEL_MARKET_ORDERS,
    CANCEL_ORDERS,
    CREATE_API_KEY,
    CREATE_READONLY_API_KEY,
    DELETE_API_KEY,
    DELETE_READONLY_API_KEY,
    DERIVE_API_KEY,
    GET_API_KEYS,
    GET_BALANCE_ALLOWANCE,
    GET_CLOB_MARKET_INFO,
    GET_FEE_RATE,
    GET_LAST_TRADE_PRICE,
    GET_LAST_TRADES_PRICES,
    GET_MARKET,
    GET_MARKET_BY_TOKEN,
    GET_MARKETS,
    GET_NEG_RISK,
    GET_ORDER_BOOK,
    GET_ORDER_BOOKS,
    GET_PRICES,
    GET_READONLY_API_KEYS,
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
    OrderCancellationError,
    OrderPlacementError,
)
from ..utilities.headers import create_level_1_headers, create_level_2_headers
from ..utilities.order_builder.builder import OrderBuilder
from ..utilities.order_builder.helpers import (
    adjust_market_buy_amount,
    is_tick_size_smaller,
    order_to_json,
    price_valid,
)
from ..utilities.order_builder.model import SignedOrder
from ..utilities.signing.signer import Signer
from ..utilities.web3.helpers import (
    detect_wallet_signature_type as detect_wallet_signature_type_from_runtime,
)


def _order_type_value(order_type: OrderType) -> str:
    return getattr(order_type, "value", str(order_type))


def _display_decimal(value: Any, max_decimals: int = 6) -> str:
    return f"{float(value):.{max_decimals}f}".rstrip("0").rstrip(".")


def _signed_order_log_fields(order: SignedOrder) -> dict[str, Any]:
    maker_amount = int(order.maker_amount)
    taker_amount = int(order.taker_amount)
    maker_units = maker_amount / 1_000_000
    taker_units = taker_amount / 1_000_000
    if order.side == 0:
        price = maker_amount / taker_amount if taker_amount else None
        size = taker_units
        notional = maker_units
    else:
        price = taker_amount / maker_amount if maker_amount else None
        size = maker_units
        notional = taker_units

    expiration = int(order.expiration)
    expiration_iso = (
        datetime.fromtimestamp(expiration, tz=UTC)
        .isoformat()
        .replace("+00:00", "Z")
        if expiration
        else ""
    )
    return {
        "token_id": order.token_id,
        "side": "BUY" if order.side == 0 else "SELL",
        "maker_amount": order.maker_amount,
        "taker_amount": order.taker_amount,
        "price": price,
        "price_display": _display_decimal(price) if price is not None else "",
        "size": size,
        "size_display": _display_decimal(size),
        "notional": notional,
        "notional_display": _display_decimal(notional),
        "maker": order.maker,
        "signer": order.signer,
        "signature_type": order.signature_type,
        "expiration": expiration or "",
        "expiration_iso": expiration_iso,
        "metadata": order.metadata,
        "builder": order.builder,
    }


def _extract_http_error(exc: HTTPStatusError) -> tuple[int, dict[str, Any] | None, str]:
    status = exc.response.status_code
    try:
        error_body = exc.response.json()
        detail = str(error_body.get("error", ""))
    except json.JSONDecodeError:
        error_body = None
        detail = exc.response.text
    return status, error_body, detail


def _cancel_filter_log_fields(body: dict[str, str]) -> dict[str, Any]:
    if "market" in body:
        return {
            "cancel_scope": "condition",
            "condition_id": body["market"],
            "cancel_filter": {"condition_id": body["market"]},
        }
    if "asset_id" in body:
        return {
            "cancel_scope": "token",
            "token_id": body["asset_id"],
            "cancel_filter": {"token_id": body["asset_id"]},
        }
    return {"cancel_scope": "market", "cancel_filter": body}


def _not_cancelled_text(not_cancelled: dict[Keccak256, str]) -> str:
    return f" not_cancelled={not_cancelled}" if not_cancelled else ""


def _expiration_text(order_type: OrderType, order_fields: dict[str, Any]) -> str:
    if order_type != OrderType.GTD or not order_fields["expiration_iso"]:
        return ""
    return f" expires={order_fields['expiration_iso']}"


def _order_action_text(order_fields: dict[str, Any], log_context: dict[str, Any]) -> str:
    if log_context.get("order_source") == "market":
        requested = log_context.get("requested_amount_display", "")
        if order_fields["side"] == "BUY":
            return (
                f"MARKET BUY ${requested} -> "
                f"{order_fields['size_display']} @ {order_fields['price_display']}"
            )
        return f"MARKET SELL {requested} @ {order_fields['price_display']}"
    return f"{order_fields['side']} {order_fields['size_display']} @ {order_fields['price_display']}"


class PolymarketReadOnlyClobClient:
    """Read-only order book related operations."""

    def __init__(
        self,
        tick_size_ttl: float = 300.0,
        proxy: Optional[str] = None,
        *,
        logger: Optional[logging.Logger] = None,
        max_retries: int = 3,
        base_retry_delay: float = 0.25,
        max_retry_delay: float = 30.0,
    ) -> None:
        self.client = httpx.Client(http2=True, timeout=30.0, proxy=proxy)
        self.base_url: str = "https://clob.polymarket.com"
        self.tick_size_ttl = tick_size_ttl
        self._max_retries = max_retries
        self._base_retry_delay = base_retry_delay
        self._max_retry_delay = max_retry_delay

        # local cache
        self.__tick_sizes: dict[str, tuple[TickSize, float]] = {}
        self.__neg_risk: dict[str, bool] = {}
        self.__fee_rates: dict[str, int] = {}
        self.__fee_infos: dict[str, FeeInfo] = {}
        self.__token_condition_map: dict[str, Keccak256] = {}

        self.logger = logger or get_logger(__name__)

    def _build_url(self, endpoint: str) -> str:
        return urljoin(self.base_url, endpoint)

    def _retry_request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Execute an HTTP request with retry logic for transient failures."""
        last_error: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self.client.request(method, url, **kwargs)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt == self._max_retries:
                    raise
                delay = min(
                    self._base_retry_delay * (2 ** attempt), self._max_retry_delay
                )
                jitter = random.uniform(0, delay * 0.1)
                self.logger.warning(
                    "Connection retry %d/%d after %.2fs for %s %s: %s",
                    attempt + 1,
                    self._max_retries,
                    delay + jitter,
                    method,
                    url,
                    str(exc),
                    extra=log_extra(
                        attempt=attempt + 1,
                        max_retries=self._max_retries,
                        error_type=type(exc).__name__,
                        url=url,
                    ),
                )
                time.sleep(delay + jitter)
            else:
                if response.status_code >= 500 or response.status_code == 429:
                    if attempt == self._max_retries:
                        break
                    delay = min(
                        self._base_retry_delay * (2 ** attempt), self._max_retry_delay
                    )
                    jitter = random.uniform(0, delay * 0.1)
                    self.logger.warning(
                        "HTTP retry %d/%d after %.2fs for %s %s → %d",
                        attempt + 1,
                        self._max_retries,
                        delay + jitter,
                        method,
                        url,
                        response.status_code,
                        extra=log_extra(
                            attempt=attempt + 1,
                            max_retries=self._max_retries,
                            status_code=response.status_code,
                            url=url,
                        ),
                    )
                    time.sleep(delay + jitter)
                    continue
                return response

        # If we get here, we exhausted retries
        raise last_error or httpx.HTTPStatusError(
            f"Max retries ({self._max_retries}) exceeded",
            request=httpx.Request(method, url),
            response=httpx.Response(503),
        )

    def get_ok(self) -> str:
        response = self.client.get(self.base_url)
        response.raise_for_status()
        return cast("str", response.json())

    def detect_wallet_signature_type(
        self, address: EthAddress
    ) -> Literal[0, 1, 2, 3] | None:
        """
        Detect wallet signature type from an address.

        Returns:
            - 0 for EOA / undeployed smart contract computed address
            - 1 for Polymarket proxy wallet
            - 2 for Safe/Gnosis proxy wallet
            - 3 for Deposit wallet

        """
        return detect_wallet_signature_type_from_runtime(address)

    def get_utc_time(self) -> datetime:
        response = self.client.get(self._build_url(TIME))
        response.raise_for_status()
        return datetime.fromtimestamp(response.json(), tz=UTC)

    def get_tick_size(self, token_id: str) -> TickSize:
        cached = self.__tick_sizes.get(token_id)
        if cached is not None:
            tick_size, cached_at = cached
            if monotonic() - cached_at < self.tick_size_ttl:
                return tick_size

        params = {"token_id": token_id}
        response = self.client.get(self._build_url(GET_TICK_SIZE), params=params)
        response.raise_for_status()
        tick_size = cast("TickSize", str(response.json()["minimum_tick_size"]))
        self.__tick_sizes[token_id] = (tick_size, monotonic())

        return tick_size

    def clear_tick_size_cache(self, token_id: str | None = None) -> None:
        if token_id is None:
            self.__tick_sizes.clear()
            return
        self.__tick_sizes.pop(token_id, None)

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

    def get_clob_market_info(self, condition_id: Keccak256) -> ClobMarketInfo:
        response = self.client.get(
            self._build_url(f"{GET_CLOB_MARKET_INFO}{condition_id}")
        )
        response.raise_for_status()
        info = ClobMarketInfo(**response.json())
        for token in info.tokens:
            self.__token_condition_map[token.token_id] = condition_id
            self.__tick_sizes[token.token_id] = (
                cast("TickSize", str(info.minimum_tick_size)),
                monotonic(),
            )
            if info.fee_data is None:
                self.__fee_infos[token.token_id] = FeeInfo()
                continue

            self.__fee_infos[token.token_id] = FeeInfo(
                rate=info.fee_data.rate,
                exponent=float(info.fee_data.exponent),
            )
        return info

    def _get_market_fee_info(self, token_id: str) -> FeeInfo:
        if token_id in self.__fee_infos:
            return self.__fee_infos[token_id]

        condition_id = self.__token_condition_map.get(token_id)
        if condition_id is None:
            response = self.client.get(
                self._build_url(f"{GET_MARKET_BY_TOKEN}{token_id}")
            )
            response.raise_for_status()
            condition_id = response.json()["condition_id"]
            self.__token_condition_map[token_id] = condition_id

        self.get_clob_market_info(condition_id)
        return self.__fee_infos.get(token_id, FeeInfo())

    def _resolve_tick_size(
        self,
        token_id: str,
        tick_size: TickSize | None = None,
    ) -> TickSize:
        min_tick_size = self.get_tick_size(token_id)
        if tick_size is not None:
            if is_tick_size_smaller(tick_size, min_tick_size):
                msg = (
                    f"invalid tick size ({tick_size!s}), "
                    f"minimum for the market is {min_tick_size!s}"
                )
                raise InvalidTickSizeError(msg)
        else:
            tick_size = min_tick_size
        return tick_size

    def _resolve_fee_rate(
        self,
        token_id: str,
        user_fee_rate: int | None = None,
    ) -> int:
        market_fee_rate_bps = self.get_fee_rate_bps(token_id)
        if (
            market_fee_rate_bps > 0
            and user_fee_rate is not None
            and user_fee_rate > 0
            and user_fee_rate != market_fee_rate_bps
        ):
            msg = (
                f"invalid user provided fee rate: ({user_fee_rate}), "
                f"fee rate for the market must be {market_fee_rate_bps}"
            )
            raise InvalidFeeRateError(msg)
        return market_fee_rate_bps

    def get_midpoint(self, token_id: str) -> Midpoint:
        """Get the mid-market price for the given token."""
        params = {"token_id": token_id}
        response = self.client.get(self._build_url(MID_POINT), params=params)
        response.raise_for_status()
        return Midpoint(token_id=token_id, value=float(response.json()["mid"]))

    def get_midpoints(self, token_ids: list[str]) -> dict[str, float]:
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

    def get_spreads(self, token_ids: list[str]) -> dict[str, float]:
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

    def get_last_trade_price(self, token_id: str) -> Price:
        """Fetches the last trade price for a token_id."""
        params = {"token_id": token_id}
        response = self.client.get(
            self._build_url(GET_LAST_TRADE_PRICE), params=params
        )
        response.raise_for_status()
        return Price(**response.json(), token_id=token_id)

    def get_last_trades_prices(self, token_ids: list[str]) -> list[Price]:
        """Fetches the last trades prices for a set of token ids."""
        body = [{"token_id": token_id} for token_id in token_ids]
        response = self.client.post(self._build_url(GET_LAST_TRADES_PRICES), json=body)
        response.raise_for_status()
        return [Price(**price) for price in response.json()]

    def get_order_book(self, token_id: str) -> OrderBookSummary:
        """Get the orderbook for the given token."""
        params = {"token_id": token_id}
        response = self.client.get(self._build_url(GET_ORDER_BOOK), params=params)
        response.raise_for_status()
        order_book = OrderBookSummary(**response.json())
        if order_book.tick_size is not None:
            self.__tick_sizes[token_id] = (order_book.tick_size, monotonic())
        return order_book

    def get_order_books(self, token_ids: list[str]) -> list[OrderBookSummary]:
        """Get the orderbook for a set of tokens."""
        body = [{"token_id": token_id} for token_id in token_ids]
        response = self.client.post(self._build_url(GET_ORDER_BOOKS), json=body)
        response.raise_for_status()
        order_books = [OrderBookSummary(**obs) for obs in response.json()]
        now = monotonic()
        for order_book in order_books:
            if order_book.tick_size is not None:
                self.__tick_sizes[order_book.token_id] = (order_book.tick_size, now)
        return order_books

    def get_market(self, condition_id: Keccak256) -> ClobMarket:
        """Get a ClobMarket by condition_id."""
        response = self.client.get(self._build_url(GET_MARKET + condition_id))
        response.raise_for_status()
        return ClobMarket(**response.json())

    def get_market_ids_from_token(self, token_id: str) -> MarketIDs:
        """Resolve the parent condition and complementary token IDs for a token."""
        response = self.client.get(self._build_url(f"{GET_MARKET_BY_TOKEN}{token_id}"))
        response.raise_for_status()
        return MarketIDs(**response.json())

    def get_markets(self, next_cursor: str = "MA==") -> PaginatedResponse[ClobMarket]:
        """Get paginated ClobMarkets."""
        params = {"next_cursor": next_cursor}
        response = self.client.get(self._build_url(GET_MARKETS), params=params)
        response.raise_for_status()
        return PaginatedResponse[ClobMarket](**response.json())

    def get_all_markets(self, next_cursor: str = "MA==") -> list[ClobMarket]:
        """Recursively fetch all ClobMarkets using pagination."""
        if next_cursor == "LTE=":
            self.logger.debug("Reached the last page of markets")
            return []

        paginated_response = self.get_markets(next_cursor=next_cursor)
        current_markets = paginated_response.data
        next_page_markets = self.get_all_markets(
            next_cursor=paginated_response.next_cursor,
        )
        return current_markets + next_page_markets

    def get_crypto_outcomes(self, slugs: list[str]) -> dict[str, CryptoOutcome]:
        response = self.client.post(
            "https://polymarket.com/api/past-results",
            json={
                "includeOutcomesBySlug": True,
                "outcomesOnly": True,
                "pastEventSlugs": slugs,
            },
        )
        response.raise_for_status()
        parsed = PastResultsResponse(**response.json())
        return parsed.data.outcomes_by_slug

    def get_recent_history(
        self,
        token_id: str,
        interval: Literal["1h", "6h", "1d", "1w", "1m", "max"] = "1d",
        fidelity: int = 1,
    ) -> PriceHistory:
        """Get the recent price history of a token (up to now)."""
        min_fidelities: dict[str, int] = {
            "1h": 1,
            "6h": 1,
            "1d": 1,
            "1w": 5,
            "1m": 10,
            "max": 2,
        }

        if fidelity < min_fidelities[interval]:
            msg = (
                f"invalid filters: minimum fidelity' for '{interval}' range "
                f"is {min_fidelities.get(interval)}"
            )
            raise ValueError(msg)

        params: dict[str, int | str] = {
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
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        fidelity: int = 2,
    ) -> PriceHistory:
        """Get the price history of a token between a selected date range."""
        if start_time is None and end_time is None:
            msg = (
                "At least 'start_time' or ('start_time' and 'end_time') "
                "must be provided"
            )
            raise ValueError(msg)

        if (
            start_time
            and end_time
            and start_time + timedelta(days=15, seconds=1) < end_time
        ):
            msg = (
                "'start_time' - 'end_time' range cannot exceed 15 days. "
                "Remove 'end_time' to get prices up to now or set a shorter range."
            )
            raise ValueError(msg)

        params: dict[str, int | str] = {
            "market": token_id,
            "fidelity": fidelity,
        }
        if start_time:
            params["startTs"] = int(start_time.timestamp())
        if end_time:
            params["endTs"] = int(end_time.timestamp())

        response = self.client.get(self._build_url("/prices-history"), params=params)
        response.raise_for_status()
        return PriceHistory(**response.json(), token_id=token_id)

    def get_all_history(self, token_id: str) -> PriceHistory:
        """Get the full price history of a token."""
        return self.get_history(
            token_id=token_id,
            start_time=datetime(2020, 1, 1, tzinfo=UTC),
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.client.close()


class PolymarketClobClient(PolymarketReadOnlyClobClient):
    @staticmethod
    def _validate_post_only_order_type(
        post_only: bool | None, order_type: OrderType
    ) -> None:
        if post_only and order_type in (OrderType.FOK, OrderType.FAK):
            msg = "post_only is not supported for FOK/FAK orders"
            raise ValueError(msg)

    def __init__(
        self,
        private_key: str,
        address: EthAddress,
        creds: ApiCreds | None = None,
        chain_id: Literal[137, 80002] = POLYGON,
        signature_type: Literal[0, 1, 2, 3] | None = None,
        proxy: Optional[str] = None,
        *,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(proxy=proxy, logger=logger)
        self.address = address
        self.signer = Signer(private_key=private_key, chain_id=chain_id)
        if signature_type is None:
            signature_type = self.detect_wallet_signature_type(address)
        self.signature_type = signature_type
        self.builder = OrderBuilder(
            signer=self.signer,
            sig_type=signature_type,
            funder=address,
        )
        self.creds = creds if creds else self.create_or_derive_api_creds()

    def create_api_creds(self, nonce: int | None = None) -> ApiCreds:
        headers = create_level_1_headers(self.signer, nonce)
        response = self.client.post(self._build_url(CREATE_API_KEY), headers=headers)
        response.raise_for_status()
        return ApiCreds(**response.json())

    def derive_api_key(self, nonce: int | None = None) -> ApiCreds:
        headers = create_level_1_headers(self.signer, nonce)
        response = self.client.get(self._build_url(DERIVE_API_KEY), headers=headers)
        response.raise_for_status()
        return ApiCreds(**response.json())

    def create_or_derive_api_creds(self, nonce: int | None = None) -> ApiCreds:
        try:
            return self.create_api_creds(nonce)
        except HTTPStatusError:
            return self.derive_api_key(nonce)

    def set_api_creds(self, creds: ApiCreds) -> None:
        self.creds = creds

    def get_api_keys(self) -> list[str]:
        request_args = RequestArgs(method="GET", request_path=GET_API_KEYS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.client.get(self._build_url(GET_API_KEYS), headers=headers)
        response.raise_for_status()
        return cast("list[str]", response.json()["apiKeys"])

    def delete_api_keys(self) -> Literal["OK"]:
        request_args = RequestArgs(method="DELETE", request_path=DELETE_API_KEY)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.client.delete(self._build_url(DELETE_API_KEY), headers=headers)
        response.raise_for_status()
        return cast("Literal['OK']", response.json())

    def create_readonly_api_key(self) -> str:
        request_args = RequestArgs(method="POST", request_path=CREATE_READONLY_API_KEY)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.client.post(
            self._build_url(CREATE_READONLY_API_KEY), headers=headers
        )
        response.raise_for_status()
        return cast("str", response.json()["apiKey"])

    def get_readonly_api_keys(self) -> list[str]:
        request_args = RequestArgs(method="GET", request_path=GET_READONLY_API_KEYS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.client.get(
            self._build_url(GET_READONLY_API_KEYS), headers=headers
        )
        response.raise_for_status()
        return cast("list[str]", response.json()["readonlyApiKeys"])

    def delete_readonly_api_key(self, key: str) -> str:
        body = {"key": key}

        request_args = RequestArgs(
            method="DELETE",
            request_path=DELETE_READONLY_API_KEY,
            body=body,
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.client.request(
            "DELETE",
            self._build_url(DELETE_READONLY_API_KEY),
            headers=headers,
            content=json.dumps(body).encode("utf-8"),
        )
        response.raise_for_status()
        return cast("str", response.json())

    def get_pusd_balance(self) -> float:
        params = {
            "asset_type": "COLLATERAL",
            "signature_type": self.signature_type,
        }
        request_args = RequestArgs(method="GET", request_path=GET_BALANCE_ALLOWANCE)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.client.get(
            self._build_url(GET_BALANCE_ALLOWANCE), headers=headers, params=params
        )
        response.raise_for_status()
        return int(response.json()["balance"]) / 10**6

    def get_token_balance(self, token_id: str) -> float:
        params = {
            "asset_type": "CONDITIONAL",
            "token_id": token_id,
            "signature_type": self.signature_type,
        }
        request_args = RequestArgs(method="GET", request_path=GET_BALANCE_ALLOWANCE)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.client.get(
            self._build_url(GET_BALANCE_ALLOWANCE), headers=headers, params=params
        )
        response.raise_for_status()
        return int(response.json()["balance"]) / 10**6

    def send_heartbeat(self) -> Literal["ok"]:
        request_args = RequestArgs(method="POST", request_path="/heartbeats")
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.client.post(self._build_url("/heartbeats"), headers=headers)
        response.raise_for_status()
        status = response.json().get("status")
        if status != "ok":
            msg = f"Unexpected heartbeat response status: {status}"
            raise ValueError(msg)
        return "ok"

    def get_orders(
        self,
        order_id: str | None = None,
        condition_id: Keccak256 | None = None,
        token_id: str | None = None,
        next_cursor: str = "MA==",
    ) -> list[OpenOrder]:
        """Gets your active orders, filtered by order_id, condition_id, token_id."""
        params: dict[str, str] = {}
        if order_id:
            params["id"] = order_id
        if condition_id:
            params["market"] = condition_id
        if token_id:
            params["asset_id"] = token_id

        request_args = RequestArgs(method="GET", request_path=ORDERS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        results: list[OpenOrder] = []
        next_cursor_str: str = next_cursor if next_cursor is not None else "MA=="
        while next_cursor_str != END_CURSOR:
            params["next_cursor"] = next_cursor_str
            response = self.client.get(
                self._build_url(ORDERS), headers=headers, params=params
            )
            response.raise_for_status()
            data = response.json()
            next_cursor_str = data["next_cursor"]
            results += [OpenOrder(**order) for order in data["data"]]

        return results

    def create_order(
        self, order_args: OrderArgs, options: PartialCreateOrderOptions | None = None
    ) -> SignedOrder:
        """Creates and signs an order."""
        tick_size = self._resolve_tick_size(
            order_args.token_id,
            options.tick_size if options else None,
        )

        if not price_valid(order_args.price, tick_size):
            msg = (
                f"price ({order_args.price}), "
                f"min: {tick_size} - max: {1 - float(tick_size)}"
            )
            raise InvalidPriceError(msg)

        neg_risk = (
            options.neg_risk
            if options and options.neg_risk is not None
            else self.get_neg_risk(order_args.token_id)
        )

        return self.builder.create_order(
            order_args,
            CreateOrderOptions(
                tick_size=tick_size,
                neg_risk=neg_risk,
            ),
        )

    def post_order(
        self,
        order: SignedOrder,
        order_type: OrderType = OrderType.GTC,
        post_only: Optional[bool] = False,
        defer_exec: Optional[bool] = False,
        *,
        idempotency_key: str | None = None,
        _log_context: dict[str, Any] | None = None,
    ) -> OrderPostResponse | None:
        """
        Posts a SignedOrder.

        Args:
            order: The signed order to post.
            order_type: Order type (GTC, FOK, FAK, GTD).
            post_only: Whether the order is post-only.
            defer_exec: Whether to defer execution.
            idempotency_key: Optional idempotency key for safe retries on timeout.

        Returns:
            OrderPostResponse if successful, None if the order was rejected by
            the server (HTTP 4xx). Raises on 5xx or network errors.

        """
        trace_id, trace_token = ensure_trace_id()
        self._validate_post_only_order_type(post_only, order_type)
        start = time.monotonic()
        order_fields = _signed_order_log_fields(order)
        log_context = _log_context or {"order_source": "limit"}
        action_text = _order_action_text(order_fields, log_context)
        try:
            emit(
                self.logger,
                logging.DEBUG,
                "clob.order.post.requested",
                "Posting order: token_id=%s side=%s order_type=%s",
                order.token_id,
                order_fields["side"],
                _order_type_value(order_type),
                operation="post_order",
                phase="requested",
                trace_id=trace_id,
                order_type=_order_type_value(order_type),
                **log_context,
                post_only=post_only,
                defer_exec=defer_exec,
                idempotency_key=idempotency_key,
                **order_fields,
            )

            body = order_to_json(order, self.creds.key, order_type, post_only, defer_exec)
            serialized = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
            headers = create_level_2_headers(
                self.signer,
                self.creds,
                RequestArgs(method="POST", request_path=POST_ORDER, body=serialized),
            )
            if idempotency_key:
                headers["Idempotency-Key"] = idempotency_key

            try:
                emit(
                    self.logger,
                    logging.DEBUG,
                    "clob.order.post.submitted",
                    "Submitted order post request",
                    operation="post_order",
                    phase="submitted",
                    trace_id=trace_id,
                    order_type=_order_type_value(order_type),
                    post_only=post_only,
                    defer_exec=defer_exec,
                    idempotency_key=idempotency_key,
                    **order_fields,
                )
                response = self.client.post(
                    self._build_url("/order"),
                    headers=headers,
                    content=serialized.encode("utf-8"),
                )
                response.raise_for_status()
            except HTTPStatusError as exc:
                latency_ms = round((time.monotonic() - start) * 1000, 3)
                status, error_body, detail = _extract_http_error(exc)

                emit(
                    self.logger,
                    logging.ERROR,
                    "clob.order.post.failed",
                    "%s failed type=%s%s token_id=%s HTTP %d reason=%s in %.2fms",
                    action_text,
                    _order_type_value(order_type),
                    _expiration_text(order_type, order_fields),
                    order.token_id,
                    status,
                    detail,
                    latency_ms,
                    operation="post_order",
                    phase="failed",
                    success=False,
                    status_code=status,
                    latency_ms=latency_ms,
                    trace_id=trace_id,
                    idempotency_key=idempotency_key,
                    **log_context,
                    error_type=type(exc).__name__,
                    error_detail=detail,
                    error_body=error_body,
                    order_type=_order_type_value(order_type),
                    post_only=post_only,
                    defer_exec=defer_exec,
                    **order_fields,
                )

                # Surface as typed exception so callers can branch on retry logic
                msg = f"Order placement failed: HTTP {status} - {detail}"
                raise OrderPlacementError(
                    msg,
                    order_id=getattr(order, "order_id", None),
                    status_code=status,
                    response_body=error_body or {},
                ) from exc
            else:
                resp = OrderPostResponse(**response.json())
                latency_ms = round((time.monotonic() - start) * 1000, 3)

                level = "info" if resp.success else "warning"
                event = (
                    "clob.order.post.accepted"
                    if resp.success
                    else "clob.order.post.rejected"
                )
                emit(
                    self.logger,
                    getattr(logging, level.upper()),
                    event,
                    "%s status=%s type=%s%s notional=%s token_id=%s order_id=%s%s in %.2fms",
                    action_text,
                    resp.status,
                    _order_type_value(order_type),
                    _expiration_text(order_type, order_fields),
                    order_fields["notional_display"],
                    order.token_id,
                    resp.order_id,
                    f" reason={resp.error_msg}" if resp.error_msg else "",
                    latency_ms,
                    operation="post_order",
                    phase="accepted" if resp.success else "rejected",
                    order_id=resp.order_id,
                    success=resp.success,
                    status=resp.status,
                    latency_ms=latency_ms,
                    trace_id=trace_id,
                    idempotency_key=idempotency_key,
                    **log_context,
                    order_type=_order_type_value(order_type),
                    post_only=post_only,
                    defer_exec=defer_exec,
                    taking_amount=resp.taking_amount,
                    making_amount=resp.making_amount,
                    error_detail=resp.error_msg or None,
                    **order_fields,
                )
                return resp
        finally:
            reset_trace_id(trace_token)

    def create_and_post_order(
        self,
        order_args: OrderArgs,
        options: PartialCreateOrderOptions | None = None,
        order_type: OrderType = OrderType.GTC,
        post_only: Optional[bool] = False,
        defer_exec: Optional[bool] = False,
    ) -> OrderPostResponse | None:
        """Utility function to create and publish an order."""
        order = self.create_order(order_args, options)
        return self.post_order(
            order=order,
            order_type=order_type,
            post_only=post_only,
            defer_exec=defer_exec,
        )

    def post_orders(
        self,
        args: list[PostOrdersArgs],
        post_only: Optional[bool] = False,
        defer_exec: Optional[bool] = False,
    ) -> list[OrderPostResponse] | None:
        """Posts multiple SignedOrders at once."""
        trace_id, trace_token = ensure_trace_id()
        start = time.monotonic()
        try:
            for arg in args:
                self._validate_post_only_order_type(post_only, arg.order_type)
            emit(
                self.logger,
                logging.DEBUG,
                "clob.orders.post.requested",
                "Posting batch orders: count=%d",
                len(args),
                operation="post_orders",
                phase="requested",
                trace_id=trace_id,
                total_count=len(args),
                post_only=post_only,
                defer_exec=defer_exec,
                orders=[
                    {
                        "index": index,
                        "order_type": _order_type_value(arg.order_type),
                        **_signed_order_log_fields(arg.order),
                    }
                    for index, arg in enumerate(args)
                ],
            )

            body = [
                order_to_json(
                    arg.order,
                    self.creds.key,
                    arg.order_type,
                    post_only,
                    defer_exec,
                )
                for arg in args
            ]
            serialized = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
            headers = create_level_2_headers(
                self.signer,
                self.creds,
                RequestArgs(method="POST", request_path=POST_ORDERS, body=serialized),
            )

            try:
                response = self.client.post(
                    self._build_url("/orders"),
                    headers=headers,
                    content=serialized.encode("utf-8"),
                )
                response.raise_for_status()
            except HTTPStatusError as exc:
                latency_ms = round((time.monotonic() - start) * 1000, 3)
                status, error_body, detail = _extract_http_error(exc)

                emit(
                    self.logger,
                    logging.ERROR,
                    "clob.orders.post.failed",
                    "Batch order post failed: HTTP %d in %.2fms - %s",
                    status,
                    latency_ms,
                    detail,
                    operation="post_orders",
                    phase="failed",
                    success=False,
                    status_code=status,
                    latency_ms=latency_ms,
                    trace_id=trace_id,
                    error_type=type(exc).__name__,
                    error_detail=detail,
                    error_body=error_body,
                    total_count=len(args),
                    post_only=post_only,
                    defer_exec=defer_exec,
                )
                msg = f"Batch order placement failed: HTTP {status} - {detail}"
                raise OrderPlacementError(
                    msg,
                    status_code=status,
                    response_body=error_body or {},
                ) from exc
            else:
                order_responses: list[OrderPostResponse] = []
                for index, item in enumerate(response.json()):
                    resp = OrderPostResponse(**item)
                    order_responses.append(resp)
                    if resp.error_msg:
                        emit(
                            self.logger,
                            logging.WARNING,
                            "clob.orders.post.item_rejected",
                            "Order %d/%d post error: %s (order_id=%s)",
                            index + 1,
                            len(args),
                            resp.error_msg,
                            resp.order_id,
                            operation="post_orders",
                            phase="item_rejected",
                            index=index,
                            order_id=resp.order_id,
                            success=resp.success,
                            status=resp.status,
                            error_detail=resp.error_msg,
                            trace_id=trace_id,
                            order_type=_order_type_value(args[index].order_type),
                            **_signed_order_log_fields(args[index].order),
                        )

                latency_ms = round((time.monotonic() - start) * 1000, 3)
                success_count = sum(1 for r in order_responses if r.success)
                emit(
                    self.logger,
                logging.INFO,
                "clob.orders.post.accepted_summary",
                    "POST_BATCH count=%d/%d order_ids=%s in %.2fms",
                    success_count,
                    len(args),
                    [r.order_id for r in order_responses if r.order_id],
                    latency_ms,
                    operation="post_orders",
                    phase="accepted_summary",
                    success=success_count == len(args),
                    success_count=success_count,
                    total_count=len(args),
                    order_ids=[r.order_id for r in order_responses if r.order_id],
                    latency_ms=latency_ms,
                    trace_id=trace_id,
                )
                return order_responses
        finally:
            reset_trace_id(trace_token)

    def create_and_post_orders(
        self, args: list[OrderArgs], order_types: list[OrderType] | None = None
    ) -> list[OrderPostResponse] | None:
        """Utility function to create and publish multiple orders at once."""
        if order_types is None:
            order_types = [OrderType.GTC] * len(args)

        if len(order_types) != len(args):
            msg = "order_types must have same length as args"
            raise ValueError(msg)

        return self.post_orders(
            [
                PostOrdersArgs(
                    order=self.create_order(order_args), order_type=order_type
                )
                for order_args, order_type in zip(args, order_types, strict=True)
            ]
        )

    def calculate_market_price(
        self, token_id: str, side: str, amount: float, order_type: OrderType
    ) -> float:
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
                book.asks,
                amount,
                order_type,
            )
        if side == "SELL":
            if book.bids is None:
                msg = "No bid orders available"
                raise LiquidityError(msg)
            return self.builder.calculate_sell_market_price(
                book.bids,
                amount,
                order_type,
            )
        msg = 'Side must be "BUY" or "SELL"'
        raise ValueError(msg)

    def create_market_order(
        self,
        order_args: MarketOrderArgs,
        options: PartialCreateOrderOptions | None = None,
    ) -> SignedOrder:
        """Creates and signs a market order."""
        self._get_market_fee_info(order_args.token_id)

        tick_size = self._resolve_tick_size(
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
            msg = (
                f"price ({order_args.price}), "
                f"min: {tick_size} - max: {1 - float(tick_size)}"
            )
            raise InvalidPriceError(msg)

        if order_args.side == "BUY" and order_args.user_usdc_balance:
            fee_info = self._get_market_fee_info(order_args.token_id)
            order_args.amount = adjust_market_buy_amount(
                order_args.amount,
                order_args.user_usdc_balance,
                order_args.price,
                fee_info.rate,
                fee_info.exponent,
            )

        neg_risk = (
            options.neg_risk
            if options and options.neg_risk is not None
            else self.get_neg_risk(order_args.token_id)
        )

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
        options: PartialCreateOrderOptions | None = None,
        order_type: OrderType = OrderType.FOK,
        defer_exec: Optional[bool] = False,
    ) -> OrderPostResponse | None:
        """Utility function to create and publish a market order."""
        requested_amount = order_args.amount
        order = self.create_market_order(order_args, options)
        return self.post_order(
            order=order,
            order_type=order_type,
            post_only=False,
            defer_exec=defer_exec,
            _log_context={
                "order_source": "market",
                "requested_amount": requested_amount,
                "requested_amount_display": _display_decimal(requested_amount),
            },
        )

    def cancel_order(self, order_id: Keccak256) -> OrderCancelResponse:
        """Cancels an order."""
        trace_id, trace_token = ensure_trace_id()
        start = time.monotonic()
        body = {"orderID": order_id}
        try:
            emit(
                self.logger,
                logging.DEBUG,
                "clob.order.cancel.requested",
                "Cancelling order: %s",
                order_id,
                operation="cancel_order",
                phase="requested",
                trace_id=trace_id,
                order_id=order_id,
                requested_order_ids=[order_id],
                cancel_scope="order",
            )

            request_args = RequestArgs(method="DELETE", request_path=CANCEL, body=body)
            headers = create_level_2_headers(self.signer, self.creds, request_args)

            try:
                response = self.client.request(
                    "DELETE",
                    self._build_url(CANCEL),
                    headers=headers,
                    content=json.dumps(body).encode("utf-8"),
                )
                response.raise_for_status()
            except HTTPStatusError as exc:
                latency_ms = round((time.monotonic() - start) * 1000, 3)
                status, error_body, detail = _extract_http_error(exc)
                emit(
                    self.logger,
                    logging.ERROR,
                    "clob.order.cancel.failed",
                    "Order cancel failed id=%s HTTP %d in %.2fms - %s",
                    order_id,
                    status,
                    latency_ms,
                    detail,
                    operation="cancel_order",
                    phase="failed",
                    success=False,
                    status_code=status,
                    latency_ms=latency_ms,
                    trace_id=trace_id,
                    order_id=order_id,
                    requested_order_ids=[order_id],
                    cancel_scope="order",
                    error_type=type(exc).__name__,
                    error_detail=detail,
                    error_body=error_body,
                )
                msg = f"Order cancellation failed: HTTP {status} - {detail}"
                raise OrderCancellationError(msg, order_id=order_id) from exc

            resp = OrderCancelResponse(**response.json())
            latency_ms = round((time.monotonic() - start) * 1000, 3)
            cancelled = resp.canceled or []
            not_cancelled = resp.not_canceled or {}
            success = order_id in cancelled and not not_cancelled
            event = "clob.order.cancel.accepted" if success else "clob.order.cancel.partial"
            emit(
                self.logger,
                logging.INFO if success else logging.WARNING,
                event,
                "CANCEL order_id=%s%s in %.2fms",
                order_id,
                _not_cancelled_text(not_cancelled),
                latency_ms,
                operation="cancel_order",
                phase="accepted" if success else "partial",
                order_id=order_id,
                order_ids=cancelled,
                requested_order_ids=[order_id],
                cancelled_order_ids=cancelled,
                cancelled_count=len(cancelled),
                not_cancelled=not_cancelled,
                cancel_scope="order",
                success=success,
                latency_ms=latency_ms,
                trace_id=trace_id,
            )
            return resp
        finally:
            reset_trace_id(trace_token)

    def cancel_orders(self, order_ids: list[Keccak256]) -> OrderCancelResponse:
        """Cancels multiple orders."""
        trace_id, trace_token = ensure_trace_id()
        start = time.monotonic()
        body = order_ids
        try:
            emit(
                self.logger,
                logging.DEBUG,
                "clob.orders.cancel.requested",
                "Cancelling orders: requested_order_ids=%s",
                order_ids,
                operation="cancel_orders",
                phase="requested",
                trace_id=trace_id,
                order_ids=order_ids,
                requested_order_ids=order_ids,
                cancel_scope="orders",
                total_count=len(order_ids),
            )

            request_args = RequestArgs(
                method="DELETE",
                request_path=CANCEL_ORDERS,
                body=body,
            )
            headers = create_level_2_headers(self.signer, self.creds, request_args)

            try:
                response = self.client.request(
                    "DELETE",
                    self._build_url(CANCEL_ORDERS),
                    headers=headers,
                    content=json.dumps(body).encode("utf-8"),
                )
                response.raise_for_status()
            except HTTPStatusError as exc:
                latency_ms = round((time.monotonic() - start) * 1000, 3)
                status, error_body, detail = _extract_http_error(exc)
                emit(
                    self.logger,
                    logging.ERROR,
                    "clob.orders.cancel.failed",
                    "Orders cancel failed requested=%s HTTP %d in %.2fms - %s",
                    order_ids,
                    status,
                    latency_ms,
                    detail,
                    operation="cancel_orders",
                    phase="failed",
                    success=False,
                    status_code=status,
                    latency_ms=latency_ms,
                    trace_id=trace_id,
                    order_ids=order_ids,
                    requested_order_ids=order_ids,
                    cancel_scope="orders",
                    total_count=len(order_ids),
                    error_type=type(exc).__name__,
                    error_detail=detail,
                    error_body=error_body,
                )
                msg = f"Order cancellation failed: HTTP {status} - {detail}"
                raise OrderCancellationError(msg) from exc

            resp = OrderCancelResponse(**response.json())
            latency_ms = round((time.monotonic() - start) * 1000, 3)
            cancelled = resp.canceled or []
            not_cancelled = resp.not_canceled or {}
            success = len(cancelled) == len(order_ids) and not not_cancelled
            event = "clob.orders.cancel.accepted" if success else "clob.orders.cancel.partial"
            emit(
                self.logger,
                logging.INFO if success else logging.WARNING,
                event,
                "CANCEL_ORDERS requested=%s cancelled=%s%s in %.2fms",
                order_ids,
                cancelled,
                _not_cancelled_text(not_cancelled),
                latency_ms,
                operation="cancel_orders",
                phase="accepted" if success else "partial",
                order_ids=cancelled,
                requested_order_ids=order_ids,
                cancelled_order_ids=cancelled,
                cancelled_count=len(cancelled),
                not_cancelled=not_cancelled,
                cancel_scope="orders",
                success=success,
                total_count=len(order_ids),
                latency_ms=latency_ms,
                trace_id=trace_id,
            )
            return resp
        finally:
            reset_trace_id(trace_token)

    def cancel_all(self) -> OrderCancelResponse:
        """Cancels all available orders for the user."""
        trace_id, trace_token = ensure_trace_id()
        start = time.monotonic()
        try:
            emit(
                self.logger,
                logging.DEBUG,
                "clob.orders.cancel_all.requested",
                "Cancelling all open orders",
                operation="cancel_all",
                phase="requested",
                trace_id=trace_id,
                cancel_scope="all",
            )
            request_args = RequestArgs(method="DELETE", request_path=CANCEL_ALL)
            headers = create_level_2_headers(self.signer, self.creds, request_args)

            try:
                response = self.client.delete(self._build_url(CANCEL_ALL), headers=headers)
                response.raise_for_status()
            except HTTPStatusError as exc:
                latency_ms = round((time.monotonic() - start) * 1000, 3)
                status, error_body, detail = _extract_http_error(exc)
                emit(
                    self.logger,
                    logging.ERROR,
                    "clob.orders.cancel_all.failed",
                    "Cancel all failed HTTP %d in %.2fms - %s",
                    status,
                    latency_ms,
                    detail,
                    operation="cancel_all",
                    phase="failed",
                    success=False,
                    status_code=status,
                    latency_ms=latency_ms,
                    trace_id=trace_id,
                    cancel_scope="all",
                    error_type=type(exc).__name__,
                    error_detail=detail,
                    error_body=error_body,
                )
                msg = f"Cancel all orders failed: HTTP {status} - {detail}"
                raise OrderCancellationError(msg) from exc

            resp = OrderCancelResponse(**response.json())
            latency_ms = round((time.monotonic() - start) * 1000, 3)
            cancelled = resp.canceled or []
            not_cancelled = resp.not_canceled or {}
            emit(
                self.logger,
                logging.INFO if not not_cancelled else logging.WARNING,
                "clob.orders.cancel_all.accepted"
                if not not_cancelled
                else "clob.orders.cancel_all.partial",
                "CANCEL_ALL count=%d order_ids=%s%s in %.2fms",
                len(cancelled),
                cancelled,
                _not_cancelled_text(not_cancelled),
                latency_ms,
                operation="cancel_all",
                phase="accepted" if not not_cancelled else "partial",
                order_ids=cancelled,
                requested_order_ids=[],
                cancelled_order_ids=cancelled,
                cancelled_count=len(cancelled),
                not_cancelled=not_cancelled,
                cancel_scope="all",
                success=not not_cancelled,
                latency_ms=latency_ms,
                trace_id=trace_id,
            )
            return resp
        finally:
            reset_trace_id(trace_token)

    def _cancel_orders_for_market(
        self, body: dict[str, str]
    ) -> OrderCancelResponse:
        trace_id, trace_token = ensure_trace_id()
        start = time.monotonic()
        filter_fields = _cancel_filter_log_fields(body)
        try:
            emit(
                self.logger,
                logging.DEBUG,
                "clob.orders.cancel_market.requested",
                "Cancelling market orders: cancel_filter=%s",
                filter_fields["cancel_filter"],
                operation="cancel_market_orders",
                phase="requested",
                trace_id=trace_id,
                **filter_fields,
            )
            request_args = RequestArgs(
                method="DELETE",
                request_path=CANCEL_MARKET_ORDERS,
                body=body,
            )
            headers = create_level_2_headers(self.signer, self.creds, request_args)

            try:
                response = self.client.request(
                    "DELETE",
                    self._build_url(CANCEL_MARKET_ORDERS),
                    headers=headers,
                    content=json.dumps(body).encode("utf-8"),
                )
                response.raise_for_status()
            except HTTPStatusError as exc:
                latency_ms = round((time.monotonic() - start) * 1000, 3)
                status, error_body, detail = _extract_http_error(exc)
                emit(
                    self.logger,
                    logging.ERROR,
                    "clob.orders.cancel_market.failed",
                    "Market orders cancel failed filter=%s HTTP %d in %.2fms - %s",
                    filter_fields["cancel_filter"],
                    status,
                    latency_ms,
                    detail,
                    operation="cancel_market_orders",
                    phase="failed",
                    success=False,
                    status_code=status,
                    latency_ms=latency_ms,
                    trace_id=trace_id,
                    error_type=type(exc).__name__,
                    error_detail=detail,
                    error_body=error_body,
                    **filter_fields,
                )
                msg = f"Cancel market orders failed: HTTP {status} - {detail}"
                raise OrderCancellationError(msg) from exc

            resp = OrderCancelResponse(**response.json())
            latency_ms = round((time.monotonic() - start) * 1000, 3)
            cancelled = resp.canceled or []
            not_cancelled = resp.not_canceled or {}
            emit(
                self.logger,
                logging.INFO if not not_cancelled else logging.WARNING,
                "clob.orders.cancel_market.accepted"
                if not not_cancelled
                else "clob.orders.cancel_market.partial",
                "CANCEL_%s %s count=%d order_ids=%s%s in %.2fms",
                filter_fields["cancel_scope"].upper(),
                filter_fields["cancel_filter"],
                len(cancelled),
                cancelled,
                _not_cancelled_text(not_cancelled),
                latency_ms,
                operation="cancel_market_orders",
                phase="accepted" if not not_cancelled else "partial",
                order_ids=cancelled,
                requested_order_ids=[],
                cancelled_order_ids=cancelled,
                cancelled_count=len(cancelled),
                not_cancelled=not_cancelled,
                success=not not_cancelled,
                latency_ms=latency_ms,
                trace_id=trace_id,
                **filter_fields,
            )
            return resp
        finally:
            reset_trace_id(trace_token)

    def cancel_orders_for_condition_id(
        self,
        condition_id: Keccak256,
    ) -> OrderCancelResponse:
        """Cancels all orders for both token_ids of a specific condition_id."""
        return self._cancel_orders_for_market({"market": condition_id})

    def cancel_orders_for_token_id(self, token_id: str) -> OrderCancelResponse:
        """Cancels all orders for a specific token_id."""
        return self._cancel_orders_for_market({"asset_id": token_id})

    def is_order_scoring(self, order_id: Keccak256) -> bool:
        """Check if the order is currently scoring."""
        request_args = RequestArgs(method="GET", request_path=IS_ORDER_SCORING)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.client.get(
            self._build_url(IS_ORDER_SCORING),
            headers=headers,
            params={"order_id": order_id},
        )
        response.raise_for_status()
        return cast("bool", response.json()["scoring"])

    def are_orders_scoring(self, order_ids: list[Keccak256]) -> dict[Keccak256, bool]:
        """Check if the orders are currently scoring."""
        body = order_ids
        request_args = RequestArgs(
            method="POST",
            request_path=ARE_ORDERS_SCORING,
            body=body,
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        headers["Content-Type"] = "application/json"

        response = self.client.post(
            self._build_url(ARE_ORDERS_SCORING), headers=headers, json=body
        )
        response.raise_for_status()
        return cast("dict[Keccak256, bool]", response.json())

    def get_market_rewards(self, condition_id: Keccak256) -> MarketRewards:
        """
        Get the MarketRewards for a given market (condition_id).

        - metadata, tokens, max_spread, min_size, rewards_config, market_competitiveness.
        """
        request_args = RequestArgs(method="GET", request_path="/rewards/markets/")
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.client.get(
            self._build_url("/rewards/markets/" + condition_id), headers=headers
        )
        response.raise_for_status()
        return next(MarketRewards(**market) for market in response.json()["data"])

    def get_trades(
        self,
        condition_id: Keccak256 | None = None,
        token_id: str | None = None,
        trade_id: str | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
        address: EthAddress | None = None,
        next_cursor: str | None = "MA==",
    ) -> list[PolygonTrade]:
        """Fetches the trade history for a user."""
        params: dict[str, str | int] = {}
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
        if address:
            params["maker_address"] = address

        request_args = RequestArgs(method="GET", request_path=TRADES)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        results: list[PolygonTrade] = []
        next_cursor_str: str = next_cursor if next_cursor is not None else "MA=="
        while next_cursor_str != END_CURSOR:
            params["next_cursor"] = next_cursor_str
            response = self.client.get(
                self._build_url(TRADES), headers=headers, params=params
            )
            response.raise_for_status()
            data = response.json()
            next_cursor_str = data["next_cursor"]
            results += [PolygonTrade(**trade) for trade in data["data"]]

        return results

    def get_total_rewards(self, date: datetime | None = None) -> DailyEarnedReward:
        """Get the total rewards earned on a given date."""
        if date is None:
            date = datetime.now(UTC)
        params = {
            "authenticationType": "magic",
            "date": f"{date.strftime('%Y-%m-%d')}",
        }

        request_args = RequestArgs(method="GET", request_path="/rewards/user/total")
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        params["l2Headers"] = json.dumps(headers)

        response = self.client.get(
            "https://polymarket.com/api/rewards/totalEarnings", params=params
        )
        response.raise_for_status()
        if response.json():
            return DailyEarnedReward(**response.json()[0])
        return DailyEarnedReward(
            date=date,
            asset_address="0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
            maker_address=self.address,
            earnings=0.0,
            asset_rate=0.0,
        )

    def get_reward_markets(
        self,
        query: str | None = None,
        sort_by: Literal[
            "market",
            "max_spread",
            "min_size",
            "rate_per_day",
            "spread",
            "price",
            "earnings",
            "earning_percentage",
        ]
        | None = "market",
        sort_direction: Literal["ASC", "DESC"] | None = None,
        show_favorites: bool = False,
    ) -> list[RewardMarket]:
        """Search through markets that offer rewards by query, sorted by different metrics."""
        results: list[RewardMarket] = []
        desc = {"ASC": False, "DESC": True}
        params: dict[str, bool | str] = {
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
            response = self.client.get(
                "https://polymarket.com/api/rewards/markets", params=params
            )
            response.raise_for_status()
            data = response.json()
            next_cursor = data["next_cursor"]
            results += [RewardMarket(**reward) for reward in data["data"]]

        return results
