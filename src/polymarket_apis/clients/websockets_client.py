from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
import random
import threading
import time
from collections.abc import Callable, Coroutine, Mapping, Sequence
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from heapq import nlargest, nsmallest
from json import JSONDecodeError
from typing import Any, Literal, cast, get_args, get_origin, get_type_hints

from pydantic import BaseModel, TypeAdapter, ValidationError
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from ..types.clob_types import ApiCreds
from ..types.websockets_types import (
    ActivityOrderMatchEvent,
    ActivityTradeEvent,
    AssetPriceSubscribeEvent,
    AssetPriceUpdateEvent,
    CommentEvent,
    MarketEvents,
    OrderBookSummaryEvent,
    OrderEvent,
    PriceChangeEvent,
    ReactionEvent,
    RealTimeDataEvents,
    RealTimeDataSubscription,
    SportsGameUpdate,
    TradeEvent,
    UserEvents,
)
from ..utilities._internal_log import current_or_new_trace_id, emit

logger = logging.getLogger(__name__)

DEFAULT_RECONNECT_INITIAL_DELAY = 1.0
DEFAULT_RECONNECT_MAX_DELAY = 30.0
MARKET_USER_HEARTBEAT_SECONDS = 10.0
REAL_TIME_DATA_HEARTBEAT_SECONDS = 5.0
DEFAULT_CLOSE_TIMEOUT_SECONDS = 1.0
DEFAULT_SUBSCRIPTION_ACK_TIMEOUT_SECONDS = 2.0
DEFAULT_SUBSCRIPTION_ERROR_GRACE_SECONDS = 0.2
DEFAULT_STALE_CONNECTION_RECOVERY_TIMEOUT_SECONDS = 2.0
DEFAULT_LOOP_THREAD_JOIN_TIMEOUT_SECONDS = 5.0
DEFAULT_LOOP_THREAD_SHUTDOWN_TIMEOUT_SECONDS = 2.0
DEFAULT_MESSAGE_QUEUE_MAXSIZE = 1000
DEFAULT_SYNC_CLOSE_TIMEOUT_SECONDS = 6.0
RAW_MESSAGE_PREVIEW_LIMIT = 500


def _default_user_stale_after_seconds() -> float:
    return max(MARKET_USER_HEARTBEAT_SECONDS * 6, 60.0)


def _default_real_time_data_stale_after_seconds() -> float:
    return max(REAL_TIME_DATA_HEARTBEAT_SECONDS * 6, 30.0)


MARKET_EVENT_ADAPTER: TypeAdapter[MarketEvents] = TypeAdapter(MarketEvents)
USER_EVENT_ADAPTER: TypeAdapter[UserEvents] = TypeAdapter(UserEvents)

REAL_TIME_DATA_EVENT_CLASSES: Mapping[str, type[RealTimeDataEvents]] = {
    "trades": ActivityTradeEvent,
    "orders_matched": ActivityOrderMatchEvent,
    "comment_created": CommentEvent,
    "comment_removed": CommentEvent,
    "reaction_created": ReactionEvent,
    "reaction_removed": ReactionEvent,
    "subscribe": AssetPriceSubscribeEvent,
    "update": AssetPriceUpdateEvent,
}

ParsedMarketMessage = MarketEvents | list[OrderBookSummaryEvent]
ProcessEventCallback = Callable[[Any], Any]
ProcessEventErrorPolicy = Literal["disconnect", "log"]
ParseErrorPolicy = Literal["drop", "raw"]
MessageMode = Literal["parsed", "raw"]
MessageQueueOverflowPolicy = Literal["drop_oldest", "disconnect", "reconnect"]
LocalOrderBookUpdateKind = Literal["snapshot", "delta", "ignored"]
type RealTimeDataSubscriptionInput = RealTimeDataSubscription | dict[str, Any]
_MESSAGE_QUEUE_SENTINEL = object()


class ProcessEventError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("process_event callback failed")


class ConnectionClosedBeforeStartError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Connection closed before first connect")


class MessageQueueOverflowError(RuntimeError):
    def __init__(self, channel: str, maxsize: int) -> None:
        super().__init__(
            f"Message queue overflow on {channel} channel (maxsize={maxsize})"
        )


class MessageQueueReconnectError(RuntimeError):
    def __init__(self, channel: str, maxsize: int) -> None:
        super().__init__(
            f"Message queue overflow on {channel} channel requires reconnect "
            f"(maxsize={maxsize})"
        )


class SubscriptionAckTimeoutError(TimeoutError):
    def __init__(self, action: str, subscriptions: list[dict[str, Any]]) -> None:
        super().__init__(
            f"Timed out waiting for {action} acknowledgement: {subscriptions}"
        )


@dataclass(frozen=True, slots=True)
class ConnectionHealth:
    channel: str
    url: str
    connected: bool
    closed: bool
    reconnecting: bool
    last_connect_time: datetime | None
    last_disconnect_time: datetime | None
    last_message_time: datetime | None
    last_heartbeat_sent_time: datetime | None
    last_pong_time: datetime | None
    last_process_event_error: str | None
    consecutive_failures: int

    @property
    def last_activity_time(self) -> datetime | None:
        candidates = [
            self.last_message_time,
            self.last_pong_time,
            self.last_connect_time,
        ]
        available = [candidate for candidate in candidates if candidate is not None]
        if not available:
            return None
        return max(available)


LifecycleCallback = Callable[[ConnectionHealth], Any]


@dataclass(frozen=True, slots=True)
class WebsocketCallbackConfig:
    process_event_error_policy: ProcessEventErrorPolicy = "disconnect"
    parse_error_policy: ParseErrorPolicy = "raw"
    on_connect: LifecycleCallback | None = None
    on_disconnect: LifecycleCallback | None = None
    on_reconnect: LifecycleCallback | None = None


@dataclass(frozen=True, slots=True)
class WebsocketQueueConfig:
    maxsize: int = DEFAULT_MESSAGE_QUEUE_MAXSIZE
    overflow_policy: MessageQueueOverflowPolicy = "reconnect"
    user_overflow_policy: MessageQueueOverflowPolicy = "disconnect"
    real_time_data_overflow_policy: MessageQueueOverflowPolicy | None = None
    sports_overflow_policy: MessageQueueOverflowPolicy | None = None


@dataclass(frozen=True, slots=True)
class WebsocketReconnectConfig:
    initial_delay: float = DEFAULT_RECONNECT_INITIAL_DELAY
    max_delay: float = DEFAULT_RECONNECT_MAX_DELAY
    close_timeout_seconds: float = DEFAULT_CLOSE_TIMEOUT_SECONDS
    market_stale_after_seconds: float | None = None
    user_stale_after_seconds: float | None = None
    real_time_data_stale_after_seconds: float | None = None
    reconnect_on_market_stale: bool = True
    reconnect_on_real_time_data_stale: bool = True


@dataclass(slots=True)
class _WebsocketMessage:
    channel: str
    text: str
    parse_json: bool = True
    trace_id: str = field(default_factory=current_or_new_trace_id)
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    message_size: int = field(init=False)
    json_data: object | None = field(init=False)

    def __post_init__(self) -> None:
        self.message_size = len(self.text.encode("utf-8"))
        if not self.parse_json:
            self.json_data = None
            return
        if not self.text or self.text.isspace():
            self.json_data = None
            return

        try:
            self.json_data = cast("object", json.loads(self.text))
        except JSONDecodeError:
            emit(
                logger,
                logging.WARNING,
                "ws.message.parse.json_failed",
                "Invalid JSON on websocket channel",
                channel=self.channel,
                trace_id=self.trace_id,
                received_at=self.received_at.isoformat(),
                message_size=self.message_size,
                raw_preview=self.text[:RAW_MESSAGE_PREVIEW_LIMIT],
                error_type="JSONDecodeError",
            )
            self.json_data = None


@dataclass(frozen=True, slots=True)
class LocalOrderBookSnapshot:
    token_id: str
    bids: dict[float, float]
    asks: dict[float, float]
    top_bids: tuple[tuple[float, float], ...]
    top_asks: tuple[tuple[float, float], ...]
    tick_size: float | None
    last_trade_price: float | None
    last_trade_size: float | None
    last_trade_side: str | None
    last_trade_time: datetime | None
    valid: bool
    last_snapshot_time: datetime | None
    last_update_time: datetime | None

    @property
    def best_bid(self) -> float | None:
        return self.top_bids[0][0] if self.top_bids else None

    @property
    def best_bid_size(self) -> float | None:
        return self.top_bids[0][1] if self.top_bids else None

    @property
    def best_ask(self) -> float | None:
        return self.top_asks[0][0] if self.top_asks else None

    @property
    def best_ask_size(self) -> float | None:
        return self.top_asks[0][1] if self.top_asks else None

    @property
    def second_best_bid(self) -> float | None:
        if len(self.top_bids) < 2:
            return None
        return self.top_bids[1][0]

    @property
    def second_best_bid_size(self) -> float | None:
        if len(self.top_bids) < 2:
            return None
        return self.top_bids[1][1]

    @property
    def second_best_ask(self) -> float | None:
        if len(self.top_asks) < 2:
            return None
        return self.top_asks[1][0]

    @property
    def second_best_ask_size(self) -> float | None:
        if len(self.top_asks) < 2:
            return None
        return self.top_asks[1][1]

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return round(self.best_ask - self.best_bid, 3)

    @property
    def mid_price(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return round((self.best_bid + self.best_ask) / 2, 3)

    def sorted_bids(self) -> list[tuple[float, float]]:
        return [(price, self.bids[price]) for price in sorted(self.bids, reverse=True)]

    def sorted_asks(self) -> list[tuple[float, float]]:
        return [(price, self.asks[price]) for price in sorted(self.asks)]

    def book_summary(self) -> dict[str, list[tuple[float, float]]]:
        return {
            "bids": self.sorted_bids(),
            "asks": self.sorted_asks(),
        }


class LocalOrderBookStore:
    """Low-latency local market book maintained from raw websocket text frames."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._bids_by_token: dict[str, dict[float, float]] = {}
        self._asks_by_token: dict[str, dict[float, float]] = {}
        self._best_bid_by_token: dict[str, float | None] = {}
        self._best_ask_by_token: dict[str, float | None] = {}
        self._top_bids_by_token: dict[str, tuple[tuple[float, float], ...]] = {}
        self._top_asks_by_token: dict[str, tuple[tuple[float, float], ...]] = {}
        self._tick_size_by_token: dict[str, float | None] = {}
        self._last_trade_price_by_token: dict[str, float | None] = {}
        self._last_trade_size_by_token: dict[str, float | None] = {}
        self._last_trade_side_by_token: dict[str, str | None] = {}
        self._last_trade_time_by_token: dict[str, datetime | None] = {}
        self._valid_tokens: set[str] = set()
        self._last_snapshot_time_by_token: dict[str, datetime] = {}
        self._last_update_time_by_token: dict[str, datetime] = {}
        self._update_count = 0
        self._invalid_reason: str | None = "awaiting_initial_snapshot"

    @property
    def valid(self) -> bool:
        with self._lock:
            return self._invalid_reason is None and bool(self._valid_tokens)

    @property
    def invalid_reason(self) -> str | None:
        with self._lock:
            return self._invalid_reason

    @property
    def update_count(self) -> int:
        with self._lock:
            return self._update_count

    @property
    def token_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._valid_tokens)

    @property
    def last_snapshot_time(self) -> datetime | None:
        with self._lock:
            if not self._last_snapshot_time_by_token:
                return None
            return max(self._last_snapshot_time_by_token.values())

    @property
    def last_update_time(self) -> datetime | None:
        with self._lock:
            if not self._last_update_time_by_token:
                return None
            return max(self._last_update_time_by_token.values())

    def invalidate(self, reason: str) -> None:
        with self._lock:
            self._bids_by_token.clear()
            self._asks_by_token.clear()
            self._best_bid_by_token.clear()
            self._best_ask_by_token.clear()
            self._top_bids_by_token.clear()
            self._top_asks_by_token.clear()
            self._tick_size_by_token.clear()
            self._last_trade_price_by_token.clear()
            self._last_trade_size_by_token.clear()
            self._last_trade_side_by_token.clear()
            self._last_trade_time_by_token.clear()
            self._valid_tokens.clear()
            self._last_snapshot_time_by_token.clear()
            self._last_update_time_by_token.clear()
            self._invalid_reason = reason

    def bids(self, token_id: str) -> dict[float, float]:
        with self._lock:
            return dict(self._bids_by_token.get(token_id, {}))

    def asks(self, token_id: str) -> dict[float, float]:
        with self._lock:
            return dict(self._asks_by_token.get(token_id, {}))

    def best_bid(self, token_id: str) -> float | None:
        with self._lock:
            return self._best_bid_by_token.get(token_id)

    def best_ask(self, token_id: str) -> float | None:
        with self._lock:
            return self._best_ask_by_token.get(token_id)

    def tick_size(self, token_id: str) -> float | None:
        with self._lock:
            return self._tick_size_by_token.get(token_id)

    def last_trade_price(self, token_id: str) -> float | None:
        with self._lock:
            return self._last_trade_price_by_token.get(token_id)

    def snapshot(self, token_id: str) -> LocalOrderBookSnapshot:
        with self._lock:
            return LocalOrderBookSnapshot(
                token_id=token_id,
                bids=dict(self._bids_by_token.get(token_id, {})),
                asks=dict(self._asks_by_token.get(token_id, {})),
                top_bids=self._top_bids_by_token.get(token_id, ()),
                top_asks=self._top_asks_by_token.get(token_id, ()),
                tick_size=self._tick_size_by_token.get(token_id),
                last_trade_price=self._last_trade_price_by_token.get(token_id),
                last_trade_size=self._last_trade_size_by_token.get(token_id),
                last_trade_side=self._last_trade_side_by_token.get(token_id),
                last_trade_time=self._last_trade_time_by_token.get(token_id),
                valid=token_id in self._valid_tokens and self._invalid_reason is None,
                last_snapshot_time=self._last_snapshot_time_by_token.get(token_id),
                last_update_time=self._last_update_time_by_token.get(token_id),
            )

    def apply_message_text(
        self,
        text: str,
        *,
        observed_at: datetime | None = None,
    ) -> LocalOrderBookUpdateKind | None:
        payload = json.loads(text)
        return self.apply_payload(payload, observed_at=observed_at)

    def apply_payload(
        self,
        payload: object,
        *,
        observed_at: datetime | None = None,
    ) -> LocalOrderBookUpdateKind | None:
        observed_at = observed_at or datetime.now(UTC)
        if isinstance(payload, list):
            applied_snapshot = False
            for item in payload:
                if isinstance(item, dict) and self._apply_snapshot(item, observed_at):
                    applied_snapshot = True
            return "snapshot" if applied_snapshot else "ignored"

        if not isinstance(payload, dict):
            return None

        event_type = payload.get("event_type")
        if event_type == "book":
            return "snapshot" if self._apply_snapshot(payload, observed_at) else "ignored"
        if event_type == "price_change":
            return "delta" if self._apply_delta(payload, observed_at) else "ignored"
        if event_type == "last_trade_price":
            return "delta" if self._apply_last_trade_price(payload, observed_at) else "ignored"
        if event_type == "tick_size_change":
            return "delta" if self._apply_tick_size_change(payload, observed_at) else "ignored"
        return None

    def _apply_snapshot(self, payload: dict[str, Any], observed_at: datetime) -> bool:
        token_id_obj = payload.get("asset_id")
        token_id = token_id_obj if isinstance(token_id_obj, str) else None
        if token_id is None:
            return False

        bids = self._levels_from_payload(payload.get("bids"))
        asks = self._levels_from_payload(payload.get("asks"))
        tick_size = self._float_from_payload(payload.get("tick_size"))
        last_trade_price = self._float_from_payload(payload.get("last_trade_price"))
        with self._lock:
            self._bids_by_token[token_id] = bids
            self._asks_by_token[token_id] = asks
            self._refresh_top_levels(token_id)
            if tick_size is not None:
                self._tick_size_by_token[token_id] = tick_size
            if last_trade_price is not None:
                self._last_trade_price_by_token[token_id] = last_trade_price
            self._valid_tokens.add(token_id)
            self._last_snapshot_time_by_token[token_id] = observed_at
            self._last_update_time_by_token[token_id] = observed_at
            self._update_count += 1
            self._invalid_reason = None
        return True

    def _apply_delta(self, payload: dict[str, Any], observed_at: datetime) -> bool:
        price_changes = payload.get("price_changes")
        if not isinstance(price_changes, list):
            return False

        applied = False
        with self._lock:
            for item in price_changes:
                if not isinstance(item, dict):
                    continue
                token_id_obj = item.get("asset_id")
                token_id = token_id_obj if isinstance(token_id_obj, str) else None
                if token_id is None or token_id not in self._valid_tokens:
                    continue

                price = self._float_from_payload(item.get("price"))
                size = self._float_from_payload(item.get("size"))
                side_obj = item.get("side")
                side = side_obj.upper() if isinstance(side_obj, str) else None
                if price is None or size is None or side not in {"BUY", "SELL"}:
                    continue

                if size > 0:
                    if side == "BUY":
                        best_ask = self._best_ask_by_token.get(token_id)
                        if best_ask is not None and price > best_ask:
                            asks = self._asks_by_token.setdefault(token_id, {})
                            for ask_price in list(asks):
                                if best_ask <= ask_price < price:
                                    asks.pop(ask_price, None)
                    else:
                        best_bid = self._best_bid_by_token.get(token_id)
                        if best_bid is not None and price < best_bid:
                            bids = self._bids_by_token.setdefault(token_id, {})
                            for bid_price in list(bids):
                                if price < bid_price <= best_bid:
                                    bids.pop(bid_price, None)

                levels = (
                    self._bids_by_token.setdefault(token_id, {})
                    if side == "BUY"
                    else self._asks_by_token.setdefault(token_id, {})
                )
                if size == 0:
                    levels.pop(price, None)
                else:
                    levels[price] = size

                self._refresh_top_levels(token_id)
                self._last_update_time_by_token[token_id] = observed_at
                applied = True

            if applied:
                self._update_count += 1
        return applied

    def _apply_last_trade_price(
        self,
        payload: dict[str, Any],
        observed_at: datetime,
    ) -> bool:
        token_id_obj = payload.get("asset_id")
        token_id = token_id_obj if isinstance(token_id_obj, str) else None
        price = self._float_from_payload(payload.get("price"))
        if token_id is None or price is None:
            return False

        size = self._float_from_payload(payload.get("size"))
        side_obj = payload.get("side")
        side = side_obj if isinstance(side_obj, str) and side_obj in {"BUY", "SELL"} else None
        with self._lock:
            self._last_trade_price_by_token[token_id] = price
            self._last_trade_size_by_token[token_id] = size
            self._last_trade_side_by_token[token_id] = side
            self._last_trade_time_by_token[token_id] = observed_at
            self._last_update_time_by_token[token_id] = observed_at
            self._update_count += 1
        return True

    def _apply_tick_size_change(
        self,
        payload: dict[str, Any],
        observed_at: datetime,
    ) -> bool:
        token_id_obj = payload.get("asset_id")
        token_id = token_id_obj if isinstance(token_id_obj, str) else None
        tick_size = self._float_from_payload(payload.get("new_tick_size"))
        if token_id is None or tick_size is None:
            return False

        with self._lock:
            self._tick_size_by_token[token_id] = tick_size
            self._last_update_time_by_token[token_id] = observed_at
            self._update_count += 1
        return True

    @classmethod
    def _levels_from_payload(cls, payload: object) -> dict[float, float]:
        if not isinstance(payload, list):
            return {}

        levels: dict[float, float] = {}
        for item in payload:
            if not isinstance(item, dict):
                continue
            price = cls._float_from_payload(item.get("price"))
            size = cls._float_from_payload(item.get("size"))
            if price is None or size is None:
                continue
            if size == 0:
                continue
            levels[price] = size
        return levels

    def _refresh_top_levels(self, token_id: str) -> None:
        bids = self._bids_by_token.get(token_id, {})
        asks = self._asks_by_token.get(token_id, {})
        top_bids = tuple(nlargest(2, bids.items()))
        top_asks = tuple(nsmallest(2, asks.items()))
        self._top_bids_by_token[token_id] = top_bids
        self._top_asks_by_token[token_id] = top_asks
        self._best_bid_by_token[token_id] = top_bids[0][0] if top_bids else None
        self._best_ask_by_token[token_id] = top_asks[0][0] if top_asks else None

    @staticmethod
    def _float_from_payload(value: object) -> float | None:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (int, float, str)):
            try:
                return float(value)
            except ValueError:
                return None
        return None


def parse_json(message: _WebsocketMessage) -> object | None:
    return message.json_data


def substitute_cls[T: BaseModel](
    cls: type[T],
    data: dict[str, Any],
    *,
    channel: str,
    raw_message: _WebsocketMessage | None = None,
) -> T | None:
    try:
        return cls(**data)
    except ValidationError as exc:
        emit(
            logger,
            logging.WARNING,
            "ws.message.parse.validation_failed",
            "Websocket payload failed model validation",
            channel=channel,
            trace_id=raw_message.trace_id if raw_message is not None else current_or_new_trace_id(),
            model=cls.__name__,
            error_type="ValidationError",
            error_detail=str(exc),
            payload_preview=str(data)[:RAW_MESSAGE_PREVIEW_LIMIT],
            raw_preview=(
                raw_message.text[:RAW_MESSAGE_PREVIEW_LIMIT]
                if raw_message is not None
                else None
            ),
            received_at=(
                raw_message.received_at.isoformat()
                if raw_message is not None
                else None
            ),
            message_size=raw_message.message_size if raw_message is not None else None,
        )
        return None


def parse_event[T: BaseModel](
    message: object,
    classes: Mapping[str, type[T]],
    event_type_field: str,
    *,
    channel: str,
    raw_message: _WebsocketMessage | None = None,
) -> T | None:
    if message is None:
        return None
    if not isinstance(message, dict):
        emit(
            logger,
            logging.WARNING,
            "ws.message.parse.invalid_payload",
            "Websocket payload was not an object",
            channel=channel,
            trace_id=raw_message.trace_id if raw_message is not None else current_or_new_trace_id(),
            event_type_field=event_type_field,
            payload_type=type(message).__name__,
            payload_preview=str(message)[:RAW_MESSAGE_PREVIEW_LIMIT],
            raw_preview=(
                raw_message.text[:RAW_MESSAGE_PREVIEW_LIMIT]
                if raw_message is not None
                else None
            ),
        )
        return None

    typ_obj = message.get(event_type_field)
    typ = typ_obj if isinstance(typ_obj, str) else None
    if typ is None:
        emit(
            logger,
            logging.WARNING,
            "ws.message.parse.invalid_payload",
            "Websocket payload is missing its event type",
            channel=channel,
            trace_id=raw_message.trace_id if raw_message is not None else current_or_new_trace_id(),
            event_type_field=event_type_field,
            payload_preview=str(message)[:RAW_MESSAGE_PREVIEW_LIMIT],
            raw_preview=(
                raw_message.text[:RAW_MESSAGE_PREVIEW_LIMIT]
                if raw_message is not None
                else None
            ),
        )
        return None

    cls = classes.get(typ)
    if cls is None:
        emit(
            logger,
            logging.WARNING,
            "ws.message.parse.unknown_event_type",
            "Unknown websocket event type",
            channel=channel,
            trace_id=raw_message.trace_id if raw_message is not None else current_or_new_trace_id(),
            event_type=typ,
            event_type_field=event_type_field,
            payload_preview=str(message)[:RAW_MESSAGE_PREVIEW_LIMIT],
            raw_preview=(
                raw_message.text[:RAW_MESSAGE_PREVIEW_LIMIT]
                if raw_message is not None
                else None
            ),
        )
        return None

    return substitute_cls(cls, message, channel=channel, raw_message=raw_message)


def parse_market_event(
    message: _WebsocketMessage,
) -> ParsedMarketMessage | None:
    payload = parse_json(message)
    if payload is None:
        return None
    if isinstance(payload, list):
        result: list[OrderBookSummaryEvent] = []
        for item in payload:
            if isinstance(item, dict):
                obj = substitute_cls(
                    OrderBookSummaryEvent,
                    item,
                    channel=message.channel,
                    raw_message=message,
                )
                if obj is not None:
                    result.append(obj)
        return result

    try:
        return MARKET_EVENT_ADAPTER.validate_python(payload)
    except ValidationError as exc:
        emit(
            logger,
            logging.WARNING,
            "ws.message.parse.validation_failed",
            "Websocket payload failed model validation",
            channel=message.channel,
            trace_id=message.trace_id,
            model="MarketEvents",
            error_type="ValidationError",
            error_detail=str(exc),
            payload_preview=str(payload)[:RAW_MESSAGE_PREVIEW_LIMIT],
            raw_preview=message.text[:RAW_MESSAGE_PREVIEW_LIMIT],
        )
        return None


def parse_user_event(message: _WebsocketMessage) -> UserEvents | None:
    payload = parse_json(message)
    if payload is None:
        return None
    try:
        return USER_EVENT_ADAPTER.validate_python(payload)
    except ValidationError as exc:
        emit(
            logger,
            logging.WARNING,
            "ws.message.parse.validation_failed",
            "Websocket payload failed model validation",
            channel=message.channel,
            trace_id=message.trace_id,
            model="UserEvents",
            error_type="ValidationError",
            error_detail=str(exc),
            payload_preview=str(payload)[:RAW_MESSAGE_PREVIEW_LIMIT],
            raw_preview=message.text[:RAW_MESSAGE_PREVIEW_LIMIT],
        )
        return None


def parse_real_time_data_event(message: _WebsocketMessage) -> RealTimeDataEvents | None:
    return parse_event(
        parse_json(message),
        REAL_TIME_DATA_EVENT_CLASSES,
        "type",
        channel=message.channel,
        raw_message=message,
    )


def parse_sports_event(message: _WebsocketMessage) -> SportsGameUpdate | None:
    payload = parse_json(message)

    if payload is None:
        return None
    if not isinstance(payload, dict):
        emit(
            logger,
            logging.WARNING,
            "ws.message.parse.invalid_payload",
            "Sports websocket payload was not an object",
            channel=message.channel,
            trace_id=message.trace_id,
            payload_type=type(payload).__name__,
            payload_preview=str(payload)[:RAW_MESSAGE_PREVIEW_LIMIT],
            raw_preview=message.text[:RAW_MESSAGE_PREVIEW_LIMIT],
        )
        return None

    return substitute_cls(
        SportsGameUpdate,
        payload,
        channel=message.channel,
        raw_message=message,
    )


def _default_process_market_event(event: Any) -> None:
    print(event, "\n")


def _default_process_user_event(event: Any) -> None:
    print(event, "\n")


def _default_process_real_time_data_event(event: Any) -> None:
    print(event, "\n")


def _default_process_sports_event(event: Any) -> None:
    print(event, "\n")


async def _invoke_process_event(
    process_event: ProcessEventCallback | None,
    event: Any,
    *,
    error_policy: ProcessEventErrorPolicy,
    channel: str,
    trace_id: str | None = None,
) -> None:
    if process_event is None:
        return

    try:
        result = process_event(event)
        if inspect.isawaitable(result):
            await result
    except Exception as exc:
        emit(
            logger,
            logging.ERROR,
            "ws.callback.failed",
            "Error while processing websocket event",
            channel=channel,
            trace_id=trace_id or current_or_new_trace_id(),
            error_type=type(exc).__name__,
            error_detail=str(exc),
        )
        if error_policy == "disconnect":
            raise ProcessEventError from exc


async def _invoke_lifecycle_callback(
    callback: LifecycleCallback | None,
    health: ConnectionHealth,
    *,
    event_name: str,
    channel: str,
) -> None:
    if callback is None:
        return

    try:
        result = callback(health)
        if inspect.isawaitable(result):
            await result
    except Exception as exc:  # noqa: BLE001
        emit(
            logger,
            logging.ERROR,
            "ws.lifecycle_callback.failed",
            "Error while processing websocket lifecycle callback",
            channel=channel,
            trace_id=current_or_new_trace_id(),
            operation=event_name,
            error_type=type(exc).__name__,
            error_detail=str(exc),
        )


def _type_allows_raw_message(annotation: object) -> bool:
    if annotation in (Any, object, _WebsocketMessage):
        return True

    origin = get_origin(annotation)
    if origin is None:
        return False

    return any(_type_allows_raw_message(arg) for arg in get_args(annotation))


def _process_event_accepts_raw_message(
    process_event: ProcessEventCallback | None,
) -> bool:
    if process_event is None:
        return False

    try:
        hints = get_type_hints(process_event)
    except Exception:  # noqa: BLE001
        # Preserve backwards compatibility for dynamically defined callbacks.
        return True

    signature = inspect.signature(process_event)
    for parameter in signature.parameters.values():
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            continue
        annotation = hints.get(parameter.name)
        if annotation is None:
            return True
        return _type_allows_raw_message(annotation)

    return True


def _extract_real_time_data_error_message(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None

    direct_message = payload.get("message")
    if isinstance(direct_message, str):
        return direct_message

    body = payload.get("body")
    if not isinstance(body, dict):
        return None

    body_message = body.get("message")
    return body_message if isinstance(body_message, str) else None


def _normalize_subscription_symbol(symbol: str | None) -> str | None:
    if symbol is None:
        return None
    normalized = symbol.strip()
    return normalized.casefold() if normalized else None


def _extract_subscription_filter_symbol(
    subscription: RealTimeDataSubscription,
) -> str | None:
    if subscription.filters is None:
        return None

    try:
        payload = json.loads(subscription.filters)
    except JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    symbol_obj = payload.get("symbol")
    return _normalize_subscription_symbol(symbol_obj) if isinstance(symbol_obj, str) else None


def _subscription_requires_positive_ack(
    subscription: RealTimeDataSubscription,
) -> bool:
    return subscription.topic in {
        "crypto_prices",
        "crypto_prices_chainlink",
        "equity_prices",
    }


def _subscription_supports_overflow_resync(
    subscription: RealTimeDataSubscription,
) -> bool:
    return subscription.topic in {
        "crypto_prices",
        "crypto_prices_chainlink",
        "equity_prices",
    }


def _subscription_ack_key(
    subscription: RealTimeDataSubscription,
) -> tuple[str, str | None] | None:
    if not _subscription_requires_positive_ack(subscription):
        return None
    return (subscription.topic, _extract_subscription_filter_symbol(subscription))


def _subscription_ack_key_from_payload(
    payload: object,
) -> tuple[str, str | None] | None:
    if not isinstance(payload, dict):
        return None

    event_type = payload.get("type")
    topic = payload.get("topic")
    if event_type != "subscribe" or not isinstance(topic, str):
        return None
    if topic not in {"crypto_prices", "crypto_prices_chainlink", "equity_prices"}:
        return None

    nested_payload = payload.get("payload")
    if not isinstance(nested_payload, dict):
        return (topic, None)

    symbol_obj = nested_payload.get("symbol")
    return (
        topic,
        _normalize_subscription_symbol(symbol_obj)
        if isinstance(symbol_obj, str)
        else None,
    )


def _subscription_ack_key_matches(
    expected_key: tuple[str, str | None],
    ack_key: tuple[str, str | None],
) -> bool:
    expected_topic, expected_symbol = expected_key
    ack_topic, ack_symbol = ack_key
    if expected_symbol is not None and ack_symbol is not None and expected_symbol != ack_symbol:
        return False

    if expected_topic == ack_topic:
        return expected_symbol is None or ack_symbol in {None, expected_symbol}

    if expected_topic == "crypto_prices_chainlink" and ack_topic == "crypto_prices":
        return expected_symbol is None or ack_symbol in {None, expected_symbol}

    return False


def _is_stale_real_time_data_connection_error(exc: ValueError) -> bool:
    return "connection_id_fk" in str(exc)


async def _wait_for_predicate(
    predicate: Callable[[], bool],
    *,
    timeout_seconds: float,
) -> None:
    if predicate():
        return

    loop = asyncio.get_running_loop()
    done = loop.create_future()

    def check() -> None:
        if done.done():
            return
        if predicate():
            done.set_result(None)
            return
        loop.call_later(0.01, check)

    loop.call_soon(check)
    async with asyncio.timeout(timeout_seconds):
        await done


def _message_mode_from_parse_messages(
    parse_messages: bool,
    message_mode: MessageMode | None,
) -> MessageMode:
    if message_mode is not None:
        return message_mode
    return "parsed" if parse_messages else "raw"


class _ManagedConnection:
    def __init__(
        self,
        *,
        channel: str,
        url: str,
        parser: Callable[[_WebsocketMessage], Any],
        process_event: ProcessEventCallback | None,
        parse_messages: bool,
        process_event_error_policy: ProcessEventErrorPolicy,
        message_mode: MessageMode | None = None,
        parse_error_policy: ParseErrorPolicy = "raw",
        on_connect: LifecycleCallback | None,
        on_disconnect: LifecycleCallback | None,
        on_reconnect: LifecycleCallback | None,
        reconnect_initial_delay: float,
        reconnect_max_delay: float,
        close_timeout_seconds: float,
        client_closed_event: asyncio.Event,
        message_queue_maxsize: int,
        message_queue_overflow_policy: MessageQueueOverflowPolicy,
        local_order_books: LocalOrderBookStore | None = None,
        stale_after_seconds: float | None = None,
        reconnect_on_stale: bool = False,
    ) -> None:
        self.channel = channel
        self.url = url
        self.parser = parser
        self.process_event = process_event
        self.message_mode = _message_mode_from_parse_messages(
            parse_messages,
            message_mode,
        )
        self.parse_messages = self.message_mode == "parsed"
        self.process_event_error_policy = process_event_error_policy
        self.parse_error_policy = parse_error_policy
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.on_reconnect = on_reconnect
        self.reconnect_initial_delay = reconnect_initial_delay
        self.reconnect_max_delay = reconnect_max_delay
        self.close_timeout_seconds = close_timeout_seconds
        self._client_closed_event = client_closed_event
        self.message_queue_overflow_policy = message_queue_overflow_policy
        self.local_order_books = local_order_books
        self._stop_event = asyncio.Event()
        self._started_event = asyncio.Event()
        self._closed_event = asyncio.Event()
        self._run_task: asyncio.Task[None] | None = None
        self._websocket: ClientConnection | None = None
        self._connected = False
        self._reconnecting = False
        self._last_connect_time: datetime | None = None
        self._last_disconnect_time: datetime | None = None
        self._last_message_time: datetime | None = None
        self._last_heartbeat_sent_time: datetime | None = None
        self._last_pong_time: datetime | None = None
        self._last_process_event_error: str | None = None
        self._consecutive_failures = 0
        self._message_queue_maxsize = message_queue_maxsize
        self._message_queue: asyncio.Queue[_WebsocketMessage | str | object] = asyncio.Queue(
            maxsize=message_queue_maxsize
        )
        self.stale_after_seconds = stale_after_seconds
        self.reconnect_on_stale = reconnect_on_stale
        self._dropped_message_count = 0
        self._last_market_data_time: datetime | None = None
        self._last_price_update_time: datetime | None = None
        self._stale_warning_active = False
        self._market_book_synchronized = channel != "market"
        self._last_book_snapshot_time: datetime | None = None
        self._market_book_invalid_reason: str | None = (
            "awaiting_initial_snapshot" if channel == "market" else None
        )

    async def run(self) -> None:
        current_task = asyncio.current_task()
        if current_task is not None:
            self._run_task = current_task
        delay = self.reconnect_initial_delay

        try:
            while not self._should_stop():
                try:
                    was_reconnecting = self._started_event.is_set()
                    self._reconnecting = was_reconnecting
                    self._reset_message_queue()
                    if was_reconnecting:
                        emit(
                            logger,
                            logging.INFO,
                            "ws.connection.reconnecting",
                            "Reconnecting websocket channel",
                            channel=self.channel,
                            trace_id=current_or_new_trace_id(),
                            url=self.url,
                            consecutive_failures=self._consecutive_failures,
                        )
                    async with connect(
                        self.url,
                        ping_interval=None,
                        close_timeout=self.close_timeout_seconds,
                    ) as websocket:
                        self._websocket = websocket
                        self._connected = True
                        self._reconnecting = False
                        self._last_connect_time = datetime.now(UTC)
                        self._last_message_time = None
                        self._last_market_data_time = None
                        self._last_price_update_time = None
                        self._stale_warning_active = False
                        if self.channel == "market":
                            self._market_book_synchronized = False
                            self._market_book_invalid_reason = (
                                "awaiting_initial_snapshot"
                            )
                            if self.local_order_books is not None:
                                self.local_order_books.invalidate(
                                    "awaiting_initial_snapshot"
                                )
                        self._consecutive_failures = 0
                        self._last_process_event_error = None
                        emit(
                            logger,
                            logging.INFO,
                            "ws.connection.connected",
                            "Connected websocket channel",
                            channel=self.channel,
                            trace_id=current_or_new_trace_id(),
                            url=self.url,
                            reconnecting=was_reconnecting,
                        )
                        await self._on_connect(websocket)
                        self._started_event.set()
                        if was_reconnecting:
                            await _invoke_lifecycle_callback(
                                self.on_reconnect,
                                self.health(),
                                event_name="reconnect",
                                channel=self.channel,
                            )
                        await _invoke_lifecycle_callback(
                            self.on_connect,
                            self.health(),
                            event_name="connect",
                            channel=self.channel,
                        )
                        delay = self.reconnect_initial_delay
                        await self._run_connected(websocket)
                except (ProcessEventError, MessageQueueOverflowError) as exc:
                    self._last_process_event_error = str(exc.__cause__ or exc)
                    self._stop_event.set()
                    break
                except MessageQueueReconnectError as exc:
                    self._last_process_event_error = str(exc)
                    emit(
                        logger,
                        logging.WARNING,
                        "ws.queue.overflow",
                        "Websocket queue overflow requires reconnect",
                        channel=self.channel,
                        trace_id=current_or_new_trace_id(),
                        queue_maxsize=self._message_queue.maxsize,
                        queue_size=self._message_queue.qsize(),
                        overflow_policy="reconnect",
                        error_type=type(exc).__name__,
                        error_detail=str(exc),
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    self._consecutive_failures += 1
                    if self._should_stop():
                        break
                    emit(
                        logger,
                        logging.ERROR,
                        "ws.connection.failed",
                        "Websocket connection error",
                        channel=self.channel,
                        trace_id=current_or_new_trace_id(),
                        url=self.url,
                        consecutive_failures=self._consecutive_failures,
                        error_type=type(exc).__name__,
                        error_detail=str(exc),
                        last_message_time=(
                            self._last_message_time.isoformat()
                            if self._last_message_time is not None
                            else None
                        ),
                        last_pong_time=(
                            self._last_pong_time.isoformat()
                            if self._last_pong_time is not None
                            else None
                        ),
                    )
                finally:
                    was_connected = self._connected
                    self._connected = False
                    if self._last_connect_time is not None:
                        self._last_disconnect_time = datetime.now(UTC)
                    if was_connected:
                        emit(
                            logger,
                            logging.INFO,
                            "ws.connection.disconnected",
                            "Disconnected websocket channel",
                            channel=self.channel,
                            trace_id=current_or_new_trace_id(),
                            url=self.url,
                            reconnecting=self._reconnecting,
                        )
                        await _invoke_lifecycle_callback(
                            self.on_disconnect,
                            self.health(),
                            event_name="disconnect",
                            channel=self.channel,
                        )
                    if self.channel == "market":
                        self._invalidate_market_book(
                            "connection_closed",
                            log_event=False,
                        )
                        if self.local_order_books is not None:
                            self.local_order_books.invalidate("connection_closed")
                    self._websocket = None

                if self._should_stop():
                    break

                self._reconnecting = True
                await asyncio.sleep(delay + random.uniform(0, delay))
                delay = min(delay * 2, self.reconnect_max_delay)
        finally:
            self._reconnecting = False
            if self._run_task is current_task:
                self._run_task = None
            self._closed_event.set()

    async def wait_started(self) -> None:
        started_wait = asyncio.create_task(self._started_event.wait())
        stop_wait = asyncio.create_task(self._stop_event.wait())
        client_closed_wait = asyncio.create_task(self._client_closed_event.wait())
        connection_closed_wait = asyncio.create_task(self._closed_event.wait())

        try:
            done, _pending = await asyncio.wait(
                {
                    started_wait,
                    stop_wait,
                    client_closed_wait,
                    connection_closed_wait,
                },
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in (
                started_wait,
                stop_wait,
                client_closed_wait,
                connection_closed_wait,
            ):
                if not task.done():
                    task.cancel()
            await asyncio.gather(
                started_wait,
                stop_wait,
                client_closed_wait,
                connection_closed_wait,
                return_exceptions=True,
            )

        if started_wait in done:
            return

        raise ConnectionClosedBeforeStartError

    async def wait_closed(self) -> None:
        await self._closed_event.wait()

    def bind_run_task(self, task: asyncio.Task[None]) -> None:
        self._run_task = task

    async def graceful_close(self) -> None:
        self._stop_event.set()
        websocket = self._websocket
        if websocket is not None:
            with contextlib.suppress(ConnectionClosed, TimeoutError):
                await asyncio.wait_for(
                    websocket.close(),
                    timeout=self.close_timeout_seconds,
                )
        await self._wait_for_run_task(timeout_seconds=self.close_timeout_seconds)

    async def close(self) -> None:
        if self.channel == "user":
            await self.graceful_close()
            return
        await self._force_close()

    async def abort(self) -> None:
        await self._force_close()

    async def _force_close(self) -> None:
        self._stop_event.set()
        await self._wait_for_run_task(timeout_seconds=0.0)

    async def _wait_for_run_task(self, *, timeout_seconds: float) -> None:
        run_task = self._run_task
        if run_task is None or run_task is asyncio.current_task():
            return

        try:
            await asyncio.wait_for(
                asyncio.shield(run_task),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await run_task

    @property
    def last_pong_time(self) -> datetime | None:
        return self._last_pong_time

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def market_book_synchronized(self) -> bool:
        return self._market_book_synchronized

    @property
    def last_book_snapshot_time(self) -> datetime | None:
        return self._last_book_snapshot_time

    @property
    def market_book_invalid_reason(self) -> str | None:
        return self._market_book_invalid_reason

    def health(self) -> ConnectionHealth:
        return ConnectionHealth(
            channel=self.channel,
            url=self.url,
            connected=self._connected,
            closed=self._stop_event.is_set() or self._client_closed_event.is_set(),
            reconnecting=self._reconnecting,
            last_connect_time=self._last_connect_time,
            last_disconnect_time=self._last_disconnect_time,
            last_message_time=self._last_message_time,
            last_heartbeat_sent_time=self._last_heartbeat_sent_time,
            last_pong_time=self._last_pong_time,
            last_process_event_error=self._last_process_event_error,
            consecutive_failures=self._consecutive_failures,
        )

    async def get_health(self) -> ConnectionHealth:
        return self.health()

    async def get_market_book_synchronized(self) -> bool:
        return self.market_book_synchronized

    async def get_last_book_snapshot_time(self) -> datetime | None:
        return self.last_book_snapshot_time

    async def get_market_book_invalid_reason(self) -> str | None:
        return self.market_book_invalid_reason

    def is_healthy(self, max_silence_seconds: float | None = None) -> bool:
        if not self._connected or self._should_stop():
            return False

        last_activity_time = self.health().last_activity_time
        if last_activity_time is None:
            return False

        timeout_seconds = (
            max_silence_seconds
            if max_silence_seconds is not None
            else self._default_health_timeout_seconds()
        )
        return (datetime.now(UTC) - last_activity_time).total_seconds() <= timeout_seconds

    async def get_is_healthy(self, max_silence_seconds: float | None = None) -> bool:
        return self.is_healthy(max_silence_seconds=max_silence_seconds)

    async def _on_connect(self, websocket: ClientConnection) -> None:
        del websocket

    async def _run_connected(self, websocket: ClientConnection) -> None:
        heartbeat_task = self._create_heartbeat_task(websocket)
        stale_task = self._create_stale_monitor_task()
        processor_task = asyncio.create_task(self._process_message_queue())
        reader_task = asyncio.create_task(self._read_messages(websocket))
        try:
            await self._after_connected_tasks_started(websocket)
            done, _pending = await asyncio.wait(
                {reader_task, processor_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if processor_task in done:
                await websocket.close()
                await processor_task
                await reader_task
            else:
                await reader_task
                await self._enqueue_queue_sentinel()
                await processor_task
        finally:
            if not processor_task.done():
                await self._enqueue_queue_sentinel()
            for task in (reader_task, processor_task):
                if not task.done():
                    task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader_task
            with contextlib.suppress(asyncio.CancelledError):
                await processor_task
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat_task
            if stale_task is not None:
                stale_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stale_task

    async def _read_messages(self, websocket: ClientConnection) -> None:
        async for incoming in websocket:
            if not isinstance(incoming, str):
                emit(
                    logger,
                    logging.WARNING,
                    "ws.message.parse.invalid_payload",
                    "Ignoring non-text websocket frame",
                    channel=self.channel,
                    trace_id=current_or_new_trace_id(),
                    payload_type=type(incoming).__name__,
                )
                continue

            self._last_message_time = datetime.now(UTC)
            if not incoming or incoming.isspace():
                continue
            if await self._handle_control_message(websocket, incoming):
                continue

            self._observe_raw_market_message(incoming)
            if self.message_mode == "raw":
                await self._enqueue_message(incoming)
            else:
                raw_message = _WebsocketMessage(
                    channel=self.channel,
                    text=incoming,
                )
                await self._enqueue_message(raw_message)
            if self._should_stop():
                break

    async def _process_message_queue(self) -> None:
        while True:
            item = await self._message_queue.get()
            try:
                if item is _MESSAGE_QUEUE_SENTINEL:
                    return
                await self._dispatch_message(cast("_WebsocketMessage | str", item))
                if self._should_stop():
                    return
            finally:
                self._message_queue.task_done()

    async def _enqueue_message(self, message: _WebsocketMessage | str) -> None:
        if self._message_queue.full():
            overflow_policy = self._effective_message_queue_overflow_policy()
            if self.channel == "market":
                self._invalidate_market_book("queue_overflow")
            trace_id = (
                message.trace_id
                if isinstance(message, _WebsocketMessage)
                else current_or_new_trace_id()
            )
            if overflow_policy == "disconnect":
                emit(
                    logger,
                    logging.ERROR,
                    "ws.queue.overflow",
                    "Websocket queue overflow detected",
                    channel=self.channel,
                    trace_id=trace_id,
                    queue_maxsize=self._message_queue.maxsize,
                    queue_size=self._message_queue.qsize(),
                    overflow_policy=overflow_policy,
                )
                raise MessageQueueOverflowError(
                    self.channel,
                    self._message_queue.maxsize,
                )
            if overflow_policy == "reconnect":
                emit(
                    logger,
                    logging.ERROR,
                    "ws.queue.overflow",
                    "Websocket queue overflow detected",
                    channel=self.channel,
                    trace_id=trace_id,
                    queue_maxsize=self._message_queue.maxsize,
                    queue_size=self._message_queue.qsize(),
                    overflow_policy=overflow_policy,
                )
                raise MessageQueueReconnectError(
                    self.channel,
                    self._message_queue.maxsize,
                )
            with contextlib.suppress(asyncio.QueueEmpty):
                dropped = self._message_queue.get_nowait()
                self._message_queue.task_done()
                if dropped is not _MESSAGE_QUEUE_SENTINEL:
                    self._dropped_message_count += 1
                    dropped_age_ms = None
                    if isinstance(dropped, _WebsocketMessage):
                        dropped_age_ms = round(
                            (datetime.now(UTC) - dropped.received_at).total_seconds()
                            * 1000,
                            3,
                        )
                    emit(
                        logger,
                        logging.WARNING,
                        "ws.queue.drop_oldest",
                        "Dropped oldest pending websocket message",
                        channel=self.channel,
                        trace_id=trace_id,
                        queue_maxsize=self._message_queue.maxsize,
                        queue_size=self._message_queue.qsize(),
                        dropped_message_count=self._dropped_message_count,
                        dropped_message_age_ms=dropped_age_ms,
                    )
        await self._message_queue.put(message)

    def _observe_raw_market_message(self, message: str) -> None:
        if self.channel != "market" or self.local_order_books is None:
            return

        observed_at = self._last_message_time or datetime.now(UTC)
        try:
            update_kind = self.local_order_books.apply_message_text(
                message,
                observed_at=observed_at,
            )
        except (JSONDecodeError, TypeError, ValueError) as exc:
            self.local_order_books.invalidate("parse_failure")
            self._invalidate_market_book("parse_failure")
            emit(
                logger,
                logging.WARNING,
                "ws.market.local_order_books.parse_failed",
                "Failed to apply websocket message to local order book",
                channel=self.channel,
                trace_id=current_or_new_trace_id(),
                error_type=type(exc).__name__,
                error_detail=str(exc),
                raw_preview=message[:RAW_MESSAGE_PREVIEW_LIMIT],
            )
            return

        if update_kind == "snapshot":
            self._mark_market_book_resynchronized(observed_at)
            self._mark_feed_fresh(observed_at)
            return
        if update_kind == "delta":
            self._mark_feed_fresh(observed_at)

    async def _enqueue_queue_sentinel(self) -> None:
        while True:
            try:
                self._message_queue.put_nowait(_MESSAGE_QUEUE_SENTINEL)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    dropped = self._message_queue.get_nowait()
                    self._message_queue.task_done()
                    if dropped is not _MESSAGE_QUEUE_SENTINEL:
                        self._dropped_message_count += 1
                        trace_id = (
                            dropped.trace_id
                            if isinstance(dropped, _WebsocketMessage)
                            else current_or_new_trace_id()
                        )
                        emit(
                            logger,
                            logging.WARNING,
                            "ws.queue.drop_oldest_shutdown",
                            "Dropped pending websocket message during shutdown",
                            channel=self.channel,
                            trace_id=trace_id,
                            queue_maxsize=self._message_queue.maxsize,
                            queue_size=self._message_queue.qsize(),
                            dropped_message_count=self._dropped_message_count,
                        )
            else:
                return

    async def _dispatch_message(self, message: _WebsocketMessage | str) -> None:
        if isinstance(message, str):
            await _invoke_process_event(
                self.process_event,
                message,
                error_policy=self.process_event_error_policy,
                channel=self.channel,
                trace_id=current_or_new_trace_id(),
            )
            return

        raw_message = message
        if self.parse_messages:
            parsed = self.parser(raw_message)
            if parsed is None:
                if self.channel == "market":
                    self._invalidate_market_book("parse_failure")
                if self.parse_error_policy == "drop":
                    return
                if _process_event_accepts_raw_message(self.process_event):
                    await _invoke_process_event(
                        self.process_event,
                        raw_message,
                        error_policy=self.process_event_error_policy,
                        channel=self.channel,
                        trace_id=raw_message.trace_id,
                    )
                else:
                    emit(
                        logger,
                        logging.WARNING,
                        "ws.message.unparsed_dropped",
                        "Dropping unparsed websocket message because callback does not accept internal websocket messages",
                        channel=self.channel,
                        trace_id=raw_message.trace_id,
                        raw_preview=raw_message.text[:RAW_MESSAGE_PREVIEW_LIMIT],
                        message_size=raw_message.message_size,
                    )
                return
            self._observe_parsed_event(parsed, raw_message)
            await _invoke_process_event(
                self.process_event,
                parsed,
                error_policy=self.process_event_error_policy,
                channel=self.channel,
                trace_id=raw_message.trace_id,
            )
            return

        await _invoke_process_event(
            self.process_event,
            raw_message,
            error_policy=self.process_event_error_policy,
            channel=self.channel,
            trace_id=raw_message.trace_id,
        )

    def _invalidate_market_book(self, reason: str, *, log_event: bool = True) -> None:
        if self.channel != "market":
            return
        was_synchronized = self._market_book_synchronized
        previous_reason = self._market_book_invalid_reason
        self._market_book_synchronized = False
        self._market_book_invalid_reason = reason
        if not log_event:
            return
        if not was_synchronized and previous_reason == reason:
            return
        emit(
            logger,
            logging.WARNING,
            "ws.market.book.invalidated",
            "Market order book synchronization invalidated",
            channel=self.channel,
            trace_id=current_or_new_trace_id(),
            error_detail=reason,
            last_book_snapshot_time=(
                self._last_book_snapshot_time.isoformat()
                if self._last_book_snapshot_time is not None
                else None
            ),
        )

    def _mark_market_book_resynchronized(self, observed_at: datetime) -> None:
        if self.channel != "market":
            return
        was_synchronized = self._market_book_synchronized
        previous_reason = self._market_book_invalid_reason
        self._market_book_synchronized = True
        self._market_book_invalid_reason = None
        self._last_book_snapshot_time = observed_at
        if was_synchronized:
            return
        emit(
            logger,
            logging.INFO,
            "ws.market.book.resynchronized",
            "Market order book synchronization restored from full snapshot",
            channel=self.channel,
            trace_id=current_or_new_trace_id(),
            resumed_at=observed_at.isoformat(),
            error_detail=previous_reason,
        )

    def _create_heartbeat_task(
        self, websocket: ClientConnection
    ) -> asyncio.Task[None] | None:
        interval = self._heartbeat_interval_seconds()
        if interval is None:
            return None

        return asyncio.create_task(self._heartbeat_loop(websocket, interval))

    def _create_stale_monitor_task(self) -> asyncio.Task[None] | None:
        if self.stale_after_seconds is None:
            return None
        return asyncio.create_task(self._stale_monitor_loop())

    async def _heartbeat_loop(
        self,
        websocket: ClientConnection,
        interval: float,
    ) -> None:
        while not self._should_stop():
            await asyncio.sleep(interval)
            if self._should_stop():
                return
            self._last_heartbeat_sent_time = datetime.now(UTC)
            await self._send_heartbeat(websocket)

    async def _stale_monitor_loop(self) -> None:
        stale_after_seconds = self.stale_after_seconds
        if stale_after_seconds is None:
            return

        poll_interval = min(max(stale_after_seconds / 2, 0.05), 5.0)
        while not self._should_stop():
            await asyncio.sleep(poll_interval)
            stale_reference = self._stale_reference_time()
            if stale_reference is None:
                continue
            silence_seconds = (datetime.now(UTC) - stale_reference).total_seconds()
            if silence_seconds < stale_after_seconds or self._stale_warning_active:
                continue
            self._stale_warning_active = True
            if self.channel == "market":
                self._invalidate_market_book("snapshot_stale")
                if self.local_order_books is not None:
                    self.local_order_books.invalidate("snapshot_stale")
            emit(
                logger,
                logging.WARNING,
                self._stale_event_name(),
                "Websocket feed appears stale",
                channel=self.channel,
                trace_id=current_or_new_trace_id(),
                stale_after_seconds=stale_after_seconds,
                silence_ms=round(silence_seconds * 1000, 3),
                last_observed_time=stale_reference.isoformat(),
            )
            if not self.reconnect_on_stale:
                continue
            websocket = self._websocket
            if websocket is None:
                continue
            emit(
                logger,
                logging.WARNING,
                self._stale_reconnect_event_name(),
                "Reconnecting websocket channel after stale feed detection",
                channel=self.channel,
                trace_id=current_or_new_trace_id(),
                stale_after_seconds=stale_after_seconds,
                silence_ms=round(silence_seconds * 1000, 3),
                last_observed_time=stale_reference.isoformat(),
            )
            with contextlib.suppress(ConnectionClosed):
                await websocket.close()

    async def _send_heartbeat(self, websocket: ClientConnection) -> None:
        del websocket

    def _heartbeat_interval_seconds(self) -> float | None:
        return None

    async def _after_connected_tasks_started(
        self, websocket: ClientConnection
    ) -> None:
        del websocket

    async def _handle_control_message(
        self, websocket: ClientConnection, message: str
    ) -> bool:
        del websocket, message
        return False

    def _should_stop(self) -> bool:
        return self._stop_event.is_set() or self._client_closed_event.is_set()

    def _default_health_timeout_seconds(self) -> float:
        interval = self._heartbeat_interval_seconds()
        if interval is None:
            return 30.0
        return max(interval * 3, interval + 5.0)

    def _effective_message_queue_overflow_policy(self) -> MessageQueueOverflowPolicy:
        return self.message_queue_overflow_policy

    def _reset_message_queue(self) -> None:
        self._message_queue = asyncio.Queue(maxsize=self._message_queue_maxsize)
        self._dropped_message_count = 0

    def _observe_parsed_event(self, parsed: Any, raw_message: _WebsocketMessage) -> None:
        if self.channel == "user":
            self._emit_user_event_log(parsed, raw_message)
            self._mark_feed_fresh(raw_message.received_at)
            return
        if self.channel == "market":
            if isinstance(parsed, list):
                if parsed:
                    self._mark_market_book_resynchronized(raw_message.received_at)
                    self._mark_feed_fresh(raw_message.received_at)
                return
            if isinstance(parsed, OrderBookSummaryEvent):
                self._mark_market_book_resynchronized(raw_message.received_at)
                self._mark_feed_fresh(raw_message.received_at)
                return
            if isinstance(parsed, PriceChangeEvent):
                self._mark_feed_fresh(raw_message.received_at)
                return
            return
        if self.channel == "real_time_data" and isinstance(parsed, AssetPriceUpdateEvent):
            self._mark_feed_fresh(raw_message.received_at, price_update=True)

    def _emit_user_event_log(self, parsed: Any, raw_message: _WebsocketMessage) -> None:
        if isinstance(parsed, OrderEvent):
            emit(
                logger,
                logging.INFO,
                "ws.user.order.received",
                "Received user order event",
                channel=self.channel,
                trace_id=raw_message.trace_id,
                order_id=parsed.order_id,
                token_id=parsed.token_id,
                status=parsed.status,
                side=parsed.side,
                price=parsed.price,
                size_matched=parsed.size_matched,
                original_size=parsed.original_size,
                order_type=parsed.order_type,
                condition_id=parsed.condition_id,
                maker_address=parsed.maker_address,
                outcome=parsed.outcome,
                metadata={
                    "type": parsed.type,
                    "associated_trades": parsed.associated_trades,
                    "event_owner": parsed.event_owner,
                    "order_owner": parsed.order_owner,
                    "created_at": parsed.created_at.isoformat(),
                    "timestamp": (
                        parsed.timestamp.isoformat()
                        if parsed.timestamp is not None
                        else None
                    ),
                    "expiration": (
                        parsed.expiration.isoformat()
                        if parsed.expiration is not None
                        else None
                    ),
                },
            )
            return
        if isinstance(parsed, TradeEvent):
            emit(
                logger,
                logging.INFO,
                "ws.user.trade.received",
                "Received user trade event",
                channel=self.channel,
                trace_id=raw_message.trace_id,
                token_id=parsed.token_id,
                order_id=parsed.taker_order_id,
                status=parsed.status,
                side=parsed.side,
                price=parsed.price,
                size=parsed.size,
                condition_id=parsed.condition_id,
                outcome=parsed.outcome,
                metadata={
                    "trade_id": parsed.trade_id,
                    "event_owner": parsed.event_owner,
                    "trade_owner": parsed.trade_owner,
                    "maker_orders": [
                        order.model_dump(mode="json", by_alias=False, exclude_none=True)
                        for order in parsed.maker_orders
                    ],
                    "last_update": parsed.last_update.isoformat(),
                    "matchtime": (
                        parsed.matchtime.isoformat()
                        if parsed.matchtime is not None
                        else None
                    ),
                    "timestamp": (
                        parsed.timestamp.isoformat()
                        if parsed.timestamp is not None
                        else None
                    ),
                },
            )

    def _mark_feed_fresh(
        self, observed_at: datetime, *, price_update: bool = False
    ) -> None:
        if self.channel == "market":
            self._last_market_data_time = observed_at
        elif self.channel == "user":
            self._last_message_time = observed_at
        elif self.channel == "real_time_data" and price_update:
            self._last_price_update_time = observed_at
        else:
            return

        if not self._stale_warning_active:
            return

        stale_reference = self._stale_reference_time()
        self._stale_warning_active = False
        emit(
            logger,
            logging.INFO,
            self._fresh_event_name(),
            "Websocket feed freshness recovered",
            channel=self.channel,
            trace_id=current_or_new_trace_id(),
            resumed_at=observed_at.isoformat(),
            last_observed_time=(
                stale_reference.isoformat() if stale_reference is not None else None
            ),
        )

    def _stale_reference_time(self) -> datetime | None:
        if self.channel == "market":
            return self._last_market_data_time or self._last_connect_time
        if self.channel == "user":
            return (
                self._last_message_time
                or self._last_pong_time
                or self._last_connect_time
            )
        if self.channel == "real_time_data":
            return self._last_price_update_time or self._last_connect_time
        return None

    def _stale_event_name(self) -> str:
        if self.channel == "market":
            return "ws.market.feed.stale"
        if self.channel == "user":
            return "ws.user.feed.stale"
        if self.channel == "real_time_data":
            return "ws.real_time_data.feed.stale"
        return "ws.feed.stale"

    def _fresh_event_name(self) -> str:
        if self.channel == "market":
            return "ws.market.feed.fresh"
        if self.channel == "user":
            return "ws.user.feed.fresh"
        if self.channel == "real_time_data":
            return "ws.real_time_data.feed.fresh"
        return "ws.feed.fresh"

    def _stale_reconnect_event_name(self) -> str:
        if self.channel == "market":
            return "ws.market.feed.stale_reconnect"
        if self.channel == "user":
            return "ws.user.feed.stale_reconnect"
        if self.channel == "real_time_data":
            return "ws.real_time_data.feed.stale_reconnect"
        return "ws.feed.stale_reconnect"


class _FixedSubscriptionConnection(_ManagedConnection):
    def __init__(
        self,
        *,
        channel: str,
        url: str,
        parser: Callable[[_WebsocketMessage], Any],
        process_event: ProcessEventCallback | None,
        parse_messages: bool,
        process_event_error_policy: ProcessEventErrorPolicy,
        message_mode: MessageMode | None = None,
        parse_error_policy: ParseErrorPolicy = "raw",
        on_connect: LifecycleCallback | None,
        on_disconnect: LifecycleCallback | None,
        on_reconnect: LifecycleCallback | None,
        reconnect_initial_delay: float,
        reconnect_max_delay: float,
        close_timeout_seconds: float,
        client_closed_event: asyncio.Event,
        message_queue_maxsize: int,
        message_queue_overflow_policy: MessageQueueOverflowPolicy,
        local_order_books: LocalOrderBookStore | None = None,
        stale_after_seconds: float | None = None,
        reconnect_on_stale: bool = False,
        initial_payload: dict[str, Any] | None = None,
        heartbeat_interval: float | None = None,
        heartbeat_message: str | None = None,
        respond_to_ping: bool = False,
    ) -> None:
        super().__init__(
            channel=channel,
            url=url,
            parser=parser,
            process_event=process_event,
            parse_messages=parse_messages,
            process_event_error_policy=process_event_error_policy,
            message_mode=message_mode,
            parse_error_policy=parse_error_policy,
            on_connect=on_connect,
            on_disconnect=on_disconnect,
            on_reconnect=on_reconnect,
            reconnect_initial_delay=reconnect_initial_delay,
            reconnect_max_delay=reconnect_max_delay,
            close_timeout_seconds=close_timeout_seconds,
            client_closed_event=client_closed_event,
            message_queue_maxsize=message_queue_maxsize,
            message_queue_overflow_policy=message_queue_overflow_policy,
            local_order_books=local_order_books,
            stale_after_seconds=stale_after_seconds,
            reconnect_on_stale=reconnect_on_stale,
        )
        self.initial_payload = deepcopy(initial_payload)
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_message = heartbeat_message
        self.respond_to_ping = respond_to_ping

    async def _on_connect(self, websocket: ClientConnection) -> None:
        if self.initial_payload is not None:
            await websocket.send(json.dumps(self.initial_payload))

    def _heartbeat_interval_seconds(self) -> float | None:
        return self.heartbeat_interval

    async def _send_heartbeat(self, websocket: ClientConnection) -> None:
        if self.heartbeat_message is None:
            return
        await websocket.send(self.heartbeat_message)

    async def _handle_control_message(
        self, websocket: ClientConnection, message: str
    ) -> bool:
        if self.respond_to_ping and message == "ping":
            self._last_pong_time = datetime.now(UTC)
            await websocket.send("pong")
            return True

        if message == "PONG":
            self._last_pong_time = datetime.now(UTC)
            return True

        return False


class AsyncChannelConnection(_FixedSubscriptionConnection):
    pass


class _DynamicSubscriptionConnection(_ManagedConnection):
    def __init__(
        self,
        *,
        url: str,
        subscriptions: Sequence[RealTimeDataSubscriptionInput],
        process_event: ProcessEventCallback | None,
        parse_messages: bool,
        process_event_error_policy: ProcessEventErrorPolicy,
        message_mode: MessageMode | None = None,
        parse_error_policy: ParseErrorPolicy = "raw",
        on_connect: LifecycleCallback | None,
        on_disconnect: LifecycleCallback | None,
        on_reconnect: LifecycleCallback | None,
        reconnect_initial_delay: float,
        reconnect_max_delay: float,
        close_timeout_seconds: float,
        client_closed_event: asyncio.Event,
        message_queue_maxsize: int,
        message_queue_overflow_policy: MessageQueueOverflowPolicy,
        stale_after_seconds: float | None = None,
        reconnect_on_stale: bool = False,
    ) -> None:
        super().__init__(
            channel="real_time_data",
            url=url,
            parser=parse_real_time_data_event,
            process_event=process_event,
            parse_messages=parse_messages,
            process_event_error_policy=process_event_error_policy,
            message_mode=message_mode,
            parse_error_policy=parse_error_policy,
            on_connect=on_connect,
            on_disconnect=on_disconnect,
            on_reconnect=on_reconnect,
            reconnect_initial_delay=reconnect_initial_delay,
            reconnect_max_delay=reconnect_max_delay,
            close_timeout_seconds=close_timeout_seconds,
            client_closed_event=client_closed_event,
            message_queue_maxsize=message_queue_maxsize,
            message_queue_overflow_policy=message_queue_overflow_policy,
            stale_after_seconds=stale_after_seconds,
            reconnect_on_stale=reconnect_on_stale,
        )
        self._subscription_lock = asyncio.Lock()
        self._current_subscriptions: list[RealTimeDataSubscription] = []
        self._subscription_keys: set[str] = set()
        self._task: asyncio.Task[None] | None = None
        self._startup_subscriptions_ready = asyncio.Event()
        self._pending_subscription_error: asyncio.Future[None] | None = None
        self._pending_subscription_ack: asyncio.Future[None] | None = None
        self._pending_subscription_ack_keys: set[tuple[str, str | None]] = set()
        self._replace_subscriptions(list(subscriptions))

    @property
    def current_subscriptions(self) -> list[dict[str, object]]:
        return [
            subscription.to_wire_dict() for subscription in self._current_subscriptions
        ]

    async def get_current_subscriptions(self) -> list[dict[str, object]]:
        return self.current_subscriptions

    async def wait_started(self) -> None:
        await super().wait_started()
        await self._startup_subscriptions_ready.wait()

    async def _start(self) -> _DynamicSubscriptionConnection:
        self._task = asyncio.create_task(self.run())
        await self.wait_started()
        return self

    def _replace_subscriptions(
        self, subscriptions: Sequence[RealTimeDataSubscriptionInput]
    ) -> None:
        normalized = [
            _coerce_real_time_data_subscription(subscription) for subscription in subscriptions
        ]
        expanded: list[RealTimeDataSubscription] = []
        keys: set[str] = set()
        for subscription in normalized:
            for cache_entry in subscription.expand():
                cache_key = cache_entry.cache_key()
                if cache_key in keys:
                    continue
                keys.add(cache_key)
                expanded.append(cache_entry)
        self._current_subscriptions = expanded
        self._subscription_keys = keys


class AsyncRealTimeDataConnection(_DynamicSubscriptionConnection):
    def _effective_message_queue_overflow_policy(self) -> MessageQueueOverflowPolicy:
        configured_policy = self.message_queue_overflow_policy
        if configured_policy != "drop_oldest":
            return configured_policy
        if not self._current_subscriptions:
            return configured_policy
        if any(
            _subscription_supports_overflow_resync(subscription)
            for subscription in self._current_subscriptions
        ):
            return "reconnect"
        return configured_policy

    async def subscribe(self, subscriptions: Sequence[RealTimeDataSubscriptionInput]) -> None:
        payload_subscriptions: list[RealTimeDataSubscription] = []

        async with self._subscription_lock:
            for subscription in subscriptions:
                normalized = _coerce_real_time_data_subscription(subscription)
                cache_entries = normalized.expand()
                if all(
                    entry.cache_key() in self._subscription_keys
                    for entry in cache_entries
                ):
                    continue
                payload_subscriptions.append(normalized)

            if not payload_subscriptions:
                return

            if self._websocket is not None:
                await self._send_subscription_request(
                    action="subscribe",
                    subscriptions=payload_subscriptions,
                )

            for normalized in payload_subscriptions:
                for cache_entry in normalized.expand():
                    cache_key = cache_entry.cache_key()
                    if cache_key in self._subscription_keys:
                        continue
                    self._subscription_keys.add(cache_key)
                    self._current_subscriptions.append(cache_entry)

    async def unsubscribe(self, subscriptions: Sequence[RealTimeDataSubscriptionInput]) -> None:
        normalized_subscriptions = [
            _coerce_real_time_data_subscription(subscription) for subscription in subscriptions
        ]

        async with self._subscription_lock:
            if not normalized_subscriptions:
                return

            expanded_subscriptions = _expand_real_time_data_unsubscribe_requests(
                self._current_subscriptions,
                normalized_subscriptions,
            )
            if not expanded_subscriptions:
                return

            if self._websocket is not None:
                for expanded_subscription in expanded_subscriptions:
                    await self._send_subscription_request(
                        action="unsubscribe",
                        subscriptions=[expanded_subscription],
                    )

            self._current_subscriptions = [
                subscription
                for subscription in self._current_subscriptions
                if not any(
                    subscription.matches_unsubscribe_request(unsubscribe_request)
                    for unsubscribe_request in expanded_subscriptions
                )
            ]
            self._subscription_keys = {
                subscription.cache_key()
                for subscription in self._current_subscriptions
            }

    async def graceful_close(self) -> None:
        await super().graceful_close()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def close(self) -> None:
        await super().close()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def abort(self) -> None:
        await super().abort()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _on_connect(self, websocket: ClientConnection) -> None:
        del websocket

    async def _after_connected_tasks_started(
        self, websocket: ClientConnection
    ) -> None:
        del websocket
        self._startup_subscriptions_ready.clear()
        try:
            subscriptions = list(self._current_subscriptions)
            if not subscriptions:
                return
            await self._send_subscription_request(
                action="subscribe",
                subscriptions=subscriptions,
            )
        finally:
            self._startup_subscriptions_ready.set()

    def _heartbeat_interval_seconds(self) -> float | None:
        return REAL_TIME_DATA_HEARTBEAT_SECONDS

    async def _send_heartbeat(self, websocket: ClientConnection) -> None:
        await websocket.send("PING")

    async def _handle_control_message(
        self, websocket: ClientConnection, message: str
    ) -> bool:
        del websocket
        if message == "PONG":
            self._last_pong_time = datetime.now(UTC)
            return True

        return False

    async def _dispatch_message(self, message: _WebsocketMessage | str) -> None:
        payload: object | None = None
        if isinstance(message, str):
            trace_id = current_or_new_trace_id()
            with contextlib.suppress(JSONDecodeError):
                payload = json.loads(message)
        else:
            trace_id = message.trace_id
            payload = message.json_data
            if payload is None and not message.parse_json:
                with contextlib.suppress(JSONDecodeError):
                    payload = json.loads(message.text)

        error_message = _extract_real_time_data_error_message(payload)
        if error_message is not None:
            pending_error = self._pending_subscription_error
            if pending_error is not None and not pending_error.done():
                pending_error.set_exception(
                    ValueError(f"Real-time data subscription error: {payload}")
                )
                return
            emit(
                logger,
                logging.WARNING,
                "ws.subscription.error",
                "Real-time data subscription error from server",
                channel=self.channel,
                trace_id=trace_id,
                error_detail=error_message,
                payload_preview=str(payload)[:RAW_MESSAGE_PREVIEW_LIMIT],
                metadata={"subscriptions": self.current_subscriptions},
            )
            return

        ack_key = _subscription_ack_key_from_payload(payload)
        if ack_key is not None:
            pending_ack = self._pending_subscription_ack
            if pending_ack is not None and not pending_ack.done():
                matched_keys = {
                    pending_key
                    for pending_key in self._pending_subscription_ack_keys
                    if _subscription_ack_key_matches(pending_key, ack_key)
                }
                if matched_keys:
                    self._pending_subscription_ack_keys.difference_update(matched_keys)
                    if not self._pending_subscription_ack_keys:
                        pending_ack.set_result(None)

        await super()._dispatch_message(message)

    async def _send_subscription_request(
        self,
        *,
        action: Literal["subscribe", "unsubscribe"],
        subscriptions: list[RealTimeDataSubscription],
    ) -> None:
        recovered_once = False
        requested_subscriptions = [
            subscription.to_wire_dict() for subscription in subscriptions
        ]
        while True:
            websocket = self._websocket
            if websocket is None:
                return

            loop = asyncio.get_running_loop()
            pending_error = loop.create_future()
            self._pending_subscription_error = pending_error
            pending_ack: asyncio.Future[None] | None = None
            ack_keys = {
                ack_key
                for subscription in subscriptions
                if (ack_key := _subscription_ack_key(subscription)) is not None
            }
            if action == "subscribe" and ack_keys:
                pending_ack = loop.create_future()
                self._pending_subscription_ack = pending_ack
                self._pending_subscription_ack_keys = set(ack_keys)
            try:
                request_started = time.monotonic()
                emit(
                    logger,
                    logging.INFO,
                    "ws.subscription.requested",
                    "Sending real-time data subscription request",
                    channel=self.channel,
                    trace_id=current_or_new_trace_id(),
                    operation=action,
                    metadata={"subscriptions": requested_subscriptions},
                )
                await websocket.send(
                    json.dumps(
                        {
                            "action": action,
                            "subscriptions": requested_subscriptions,
                        }
                    )
                )
                if pending_ack is not None:
                    done, pending = await asyncio.wait(
                        {pending_ack, pending_error},
                        timeout=DEFAULT_SUBSCRIPTION_ACK_TIMEOUT_SECONDS,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    del pending
                    if pending_error in done:
                        await pending_error
                    if pending_ack not in done:
                        if self._websocket is None or self._websocket is not websocket:
                            continue
                        emit(
                            logger,
                            logging.ERROR,
                            "ws.subscription.timeout",
                            "Timed out waiting for real-time data subscription acknowledgement",
                            channel=self.channel,
                            trace_id=current_or_new_trace_id(),
                            operation=action,
                            metadata={"subscriptions": requested_subscriptions},
                            latency_ms=round((time.monotonic() - request_started) * 1000, 3),
                        )
                        raise SubscriptionAckTimeoutError(
                            action,
                            requested_subscriptions,
                        )
                    emit(
                        logger,
                        logging.INFO,
                        "ws.subscription.acknowledged",
                        "Real-time data subscription acknowledged",
                        channel=self.channel,
                        trace_id=current_or_new_trace_id(),
                        operation=action,
                        metadata={"subscriptions": requested_subscriptions},
                        latency_ms=round((time.monotonic() - request_started) * 1000, 3),
                    )
                else:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(
                            asyncio.shield(pending_error),
                            timeout=DEFAULT_SUBSCRIPTION_ERROR_GRACE_SECONDS,
                        )
            except ConnectionClosed:
                disconnected_websocket = websocket

                def is_reconnected(
                    stale_websocket: ClientConnection = disconnected_websocket,
                ) -> bool:
                    return (
                        self._websocket is None
                        or self._websocket is not stale_websocket
                    )

                await _wait_for_predicate(
                    is_reconnected,
                    timeout_seconds=max(
                        DEFAULT_STALE_CONNECTION_RECOVERY_TIMEOUT_SECONDS,
                        self.reconnect_max_delay + 1.0,
                    ),
                )
            except ValueError as exc:
                if recovered_once or not _is_stale_real_time_data_connection_error(exc):
                    raise
                recovered_once = True
                emit(
                    logger,
                    logging.WARNING,
                    "ws.subscription.stale_recovery",
                    "Recovering stale real-time data websocket connection",
                    channel=self.channel,
                    trace_id=current_or_new_trace_id(),
                    error_type=type(exc).__name__,
                    error_detail=str(exc),
                    metadata={"subscriptions": requested_subscriptions},
                )
                await self._recover_stale_subscription_connection(websocket)
            else:
                return
            finally:
                if self._pending_subscription_error is pending_error:
                    self._pending_subscription_error = None
                if self._pending_subscription_ack is pending_ack:
                    self._pending_subscription_ack = None
                    self._pending_subscription_ack_keys.clear()
                if pending_error.done():
                    with contextlib.suppress(Exception):
                        pending_error.exception()

    async def _recover_stale_subscription_connection(
        self,
        stale_websocket: ClientConnection,
    ) -> None:
        with contextlib.suppress(ConnectionClosed):
            await stale_websocket.close()

        await _wait_for_predicate(
            lambda: (
                self._websocket is not None
                and self._websocket is not stale_websocket
                and self.connected
                and self._startup_subscriptions_ready.is_set()
            ),
            timeout_seconds=DEFAULT_STALE_CONNECTION_RECOVERY_TIMEOUT_SECONDS,
        )

def _coerce_real_time_data_subscription(
    subscription: RealTimeDataSubscriptionInput,
) -> RealTimeDataSubscription:
    if isinstance(subscription, RealTimeDataSubscription):
        return subscription

    try:
        return RealTimeDataSubscription.model_validate(deepcopy(subscription))
    except ValidationError as exc:
        errors = exc.errors()
        if any(error.get("type") == "missing" for error in errors):
            msg = f"Invalid live data subscription shape: {subscription}"
            raise ValueError(msg) from exc
        if any(error.get("loc") == ("topic",) for error in errors):
            msg = f"Invalid real-time data subscription: {subscription}"
            raise ValueError(msg) from exc
        if any(error.get("loc") == ("type",) for error in errors):
            msg = f"Invalid real-time data subscription: {subscription}"
            raise ValueError(msg) from exc
        if any(error.get("loc") == ("filters",) for error in errors):
            msg = f"Invalid real-time data subscription filters: {subscription}"
            raise ValueError(msg) from exc
        if any(
            error.get("loc") == ("gamma_auth",)
            or error.get("loc", ())[:1] == ("gamma_auth",)
            for error in errors
        ):
            msg = f"Invalid real-time data subscription gamma_auth: {subscription}"
            raise ValueError(msg) from exc
        msg = f"Invalid real-time data subscription shape: {subscription}"
        raise ValueError(msg) from exc


def _expand_real_time_data_unsubscribe_requests(
    current_subscriptions: Sequence[RealTimeDataSubscription],
    unsubscribe_requests: Sequence[RealTimeDataSubscription],
) -> list[RealTimeDataSubscription]:
    expanded: list[RealTimeDataSubscription] = []
    seen: set[str] = set()

    for unsubscribe_request in unsubscribe_requests:
        unsubscribe_type = unsubscribe_request.type
        if unsubscribe_type != "*":
            request_key = unsubscribe_request.cache_key()
            if request_key not in seen:
                seen.add(request_key)
                expanded.append(unsubscribe_request)
            continue

        topic = unsubscribe_request.topic
        matching_types = {
            subscription.type
            for subscription in current_subscriptions
            if subscription.topic == topic
            and (
                unsubscribe_request.filters is None
                or subscription.filters == unsubscribe_request.filters
            )
        }

        for matching_type in sorted(matching_types):
            expanded_request = unsubscribe_request.model_copy(
                update={"type": matching_type}
            )
            request_key = expanded_request.cache_key()
            if request_key in seen:
                continue
            seen.add(request_key)
            expanded.append(expanded_request)

    return expanded


class AsyncPolymarketWebsocketsClient:
    """
    Factory for async websocket connections.

    Primary API:
    - open_*_connection(): returns a connection handle for explicit lifecycle control

    Convenience API:
    - run_*_stream(): opens a stream and waits until it closes
    """

    def __init__(
        self,
        *,
        callbacks: WebsocketCallbackConfig | None = None,
        queue: WebsocketQueueConfig | None = None,
        reconnect: WebsocketReconnectConfig | None = None,
    ) -> None:
        callbacks = callbacks or WebsocketCallbackConfig()
        queue = queue or WebsocketQueueConfig()
        reconnect = reconnect or WebsocketReconnectConfig()
        self.url_market = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        self.url_user = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
        self.url_real_time_data = "wss://ws-live-data.polymarket.com"
        self.url_sports = "wss://sports-api.polymarket.com/ws"
        self.process_event_error_policy = callbacks.process_event_error_policy
        self.parse_error_policy = callbacks.parse_error_policy
        self.message_queue_maxsize = queue.maxsize
        self.message_queue_overflow_policy = queue.overflow_policy
        self.user_message_queue_overflow_policy = queue.user_overflow_policy
        self.real_time_data_message_queue_overflow_policy = (
            queue.real_time_data_overflow_policy
            if queue.real_time_data_overflow_policy is not None
            else queue.overflow_policy
        )
        self.sports_message_queue_overflow_policy = (
            queue.sports_overflow_policy
            if queue.sports_overflow_policy is not None
            else queue.overflow_policy
        )
        self.on_connect = callbacks.on_connect
        self.on_disconnect = callbacks.on_disconnect
        self.on_reconnect = callbacks.on_reconnect
        self.reconnect_initial_delay = reconnect.initial_delay
        self.reconnect_max_delay = reconnect.max_delay
        self.close_timeout_seconds = reconnect.close_timeout_seconds
        self.market_stale_after_seconds = reconnect.market_stale_after_seconds
        self.user_stale_after_seconds = reconnect.user_stale_after_seconds
        self.real_time_data_stale_after_seconds = reconnect.real_time_data_stale_after_seconds
        self.reconnect_on_market_stale = reconnect.reconnect_on_market_stale
        self.reconnect_on_real_time_data_stale = reconnect.reconnect_on_real_time_data_stale
        self._closed = asyncio.Event()
        self._connections: set[_ManagedConnection] = set()
        self._connections_lock = asyncio.Lock()

    async def _ensure_open(self) -> None:
        if not self._closed.is_set():
            return

        async with self._connections_lock:
            if not self._closed.is_set():
                return
            self._closed = asyncio.Event()
            self._connections.clear()

    async def _shutdown_connections(self) -> None:
        if self._closed.is_set():
            return

        self._closed.set()
        async with self._connections_lock:
            connections = list(self._connections)

        await asyncio.gather(
            *(connection.close() for connection in connections),
            return_exceptions=True,
        )

    async def run_market_stream(
        self,
        token_ids: list[str],
        custom_feature_enabled: bool = True,
        process_event: ProcessEventCallback = _default_process_market_event,
        parse_messages: bool = True,
        message_mode: MessageMode | None = None,
        local_order_books: LocalOrderBookStore | None = None,
    ) -> None:
        """
        Convenience API: run the market stream until it closes.

        Prefer open_market_connection() when you need a handle for health checks,
        explicit shutdown, or multi-connection orchestration.
        """
        connection = await self.open_market_connection(
            token_ids=token_ids,
            custom_feature_enabled=custom_feature_enabled,
            process_event=process_event,
            parse_messages=parse_messages,
            message_mode=message_mode,
            local_order_books=local_order_books,
        )
        await connection.wait_closed()

    async def open_market_connection(
        self,
        token_ids: list[str],
        custom_feature_enabled: bool = True,
        process_event: ProcessEventCallback = _default_process_market_event,
        parse_messages: bool = True,
        message_mode: MessageMode | None = None,
        local_order_books: LocalOrderBookStore | None = None,
    ) -> AsyncChannelConnection:
        """Primary API: open a market stream and return a connection handle."""
        await self._ensure_open()
        connection = AsyncChannelConnection(
            channel="market",
            url=self.url_market,
            parser=parse_market_event,
            process_event=process_event,
            parse_messages=parse_messages,
            process_event_error_policy=self.process_event_error_policy,
            message_mode=message_mode,
            parse_error_policy=self.parse_error_policy,
            on_connect=self.on_connect,
            on_disconnect=self.on_disconnect,
            on_reconnect=self.on_reconnect,
            reconnect_initial_delay=self.reconnect_initial_delay,
            reconnect_max_delay=self.reconnect_max_delay,
            close_timeout_seconds=self.close_timeout_seconds,
            client_closed_event=self._closed,
            message_queue_maxsize=self.message_queue_maxsize,
            message_queue_overflow_policy=self.message_queue_overflow_policy,
            local_order_books=local_order_books,
            stale_after_seconds=(
                self.market_stale_after_seconds
            ),
            reconnect_on_stale=self.reconnect_on_market_stale,
            initial_payload={
                "assets_ids": token_ids,
                "type": "market",
                "custom_feature_enabled": custom_feature_enabled,
            },
            heartbeat_interval=MARKET_USER_HEARTBEAT_SECONDS,
            heartbeat_message="PING",
        )
        return await self._start_background_connection(connection)

    async def run_user_stream(
        self,
        creds: ApiCreds,
        condition_ids: list[str] | None = None,
        process_event: ProcessEventCallback = _default_process_user_event,
        parse_messages: bool = True,
        message_mode: MessageMode | None = None,
    ) -> None:
        """
        Convenience API: run the user stream until it closes.

        Prefer open_user_connection() when you need a handle for health checks,
        explicit shutdown, or multi-connection orchestration.
        """
        payload: dict[str, Any] = {
            "auth": creds.model_dump(by_alias=True),
            "type": "user",
        }
        if condition_ids is not None:
            payload["markets"] = condition_ids

        connection = await self.open_user_connection(
            creds=creds,
            condition_ids=condition_ids,
            process_event=process_event,
            parse_messages=parse_messages,
            message_mode=message_mode,
        )
        await connection.wait_closed()

    async def open_user_connection(
        self,
        creds: ApiCreds,
        condition_ids: list[str] | None = None,
        process_event: ProcessEventCallback = _default_process_user_event,
        parse_messages: bool = True,
        message_mode: MessageMode | None = None,
    ) -> AsyncChannelConnection:
        """Primary API: open a user stream and return a connection handle."""
        await self._ensure_open()
        payload: dict[str, Any] = {
            "auth": creds.model_dump(by_alias=True),
            "type": "user",
        }
        if condition_ids is not None:
            payload["markets"] = condition_ids

        connection = AsyncChannelConnection(
            channel="user",
            url=self.url_user,
            parser=parse_user_event,
            process_event=process_event,
            parse_messages=parse_messages,
            process_event_error_policy=self.process_event_error_policy,
            message_mode=message_mode,
            parse_error_policy=self.parse_error_policy,
            on_connect=self.on_connect,
            on_disconnect=self.on_disconnect,
            on_reconnect=self.on_reconnect,
            reconnect_initial_delay=self.reconnect_initial_delay,
            reconnect_max_delay=self.reconnect_max_delay,
            close_timeout_seconds=self.close_timeout_seconds,
            client_closed_event=self._closed,
            message_queue_maxsize=self.message_queue_maxsize,
            message_queue_overflow_policy=self.user_message_queue_overflow_policy,
            stale_after_seconds=(
                self.user_stale_after_seconds
                if self.user_stale_after_seconds is not None
                else _default_user_stale_after_seconds()
            ),
            initial_payload=payload,
            heartbeat_interval=MARKET_USER_HEARTBEAT_SECONDS,
            heartbeat_message="PING",
        )
        return await self._start_background_connection(connection)

    async def open_real_time_data_connection(
        self,
        subscriptions: list[RealTimeDataSubscriptionInput],
        process_event: ProcessEventCallback = _default_process_real_time_data_event,
        parse_messages: bool = True,
        message_mode: MessageMode | None = None,
    ) -> AsyncRealTimeDataConnection:
        """
        Primary API: open a real-time data stream and return a connection handle.

        This is the preferred real-time data entry point because the returned handle
        supports subscribe() and unsubscribe() after the connection starts.
        """
        await self._ensure_open()
        connection = AsyncRealTimeDataConnection(
            url=self.url_real_time_data,
            subscriptions=subscriptions,
            process_event=process_event,
            parse_messages=parse_messages,
            process_event_error_policy=self.process_event_error_policy,
            message_mode=message_mode,
            parse_error_policy=self.parse_error_policy,
            on_connect=self.on_connect,
            on_disconnect=self.on_disconnect,
            on_reconnect=self.on_reconnect,
            reconnect_initial_delay=self.reconnect_initial_delay,
            reconnect_max_delay=self.reconnect_max_delay,
            close_timeout_seconds=self.close_timeout_seconds,
            client_closed_event=self._closed,
            message_queue_maxsize=self.message_queue_maxsize,
            message_queue_overflow_policy=self.real_time_data_message_queue_overflow_policy,
            stale_after_seconds=(
                self.real_time_data_stale_after_seconds
                if self.real_time_data_stale_after_seconds is not None
                else _default_real_time_data_stale_after_seconds()
            ),
            reconnect_on_stale=self.reconnect_on_real_time_data_stale,
        )
        return await self._start_background_connection(connection)

    async def run_real_time_data_stream(
        self,
        subscriptions: list[RealTimeDataSubscriptionInput],
        process_event: ProcessEventCallback = _default_process_real_time_data_event,
        parse_messages: bool = True,
        message_mode: MessageMode | None = None,
    ) -> None:
        """
        Convenience API: run the real-time data stream until it closes.

        Prefer open_real_time_data_connection() when you need dynamic subscription
        management or explicit lifecycle control.
        """
        connection = await self.open_real_time_data_connection(
            subscriptions=subscriptions,
            process_event=process_event,
            parse_messages=parse_messages,
            message_mode=message_mode,
        )
        await connection.wait_closed()

    async def run_sports_stream(
        self,
        process_event: ProcessEventCallback = _default_process_sports_event,
        parse_messages: bool = True,
        message_mode: MessageMode | None = None,
    ) -> None:
        """
        Convenience API: run the sports stream until it closes.

        Prefer open_sports_connection() when you need a handle for health checks,
        explicit shutdown, or multi-connection orchestration.
        """
        connection = await self.open_sports_connection(
            process_event=process_event,
            parse_messages=parse_messages,
            message_mode=message_mode,
        )
        await connection.wait_closed()

    async def open_sports_connection(
        self,
        process_event: ProcessEventCallback = _default_process_sports_event,
        parse_messages: bool = True,
        message_mode: MessageMode | None = None,
    ) -> AsyncChannelConnection:
        """Primary API: open a sports stream and return a connection handle."""
        await self._ensure_open()
        connection = AsyncChannelConnection(
            channel="sports",
            url=self.url_sports,
            parser=parse_sports_event,
            process_event=process_event,
            parse_messages=parse_messages,
            process_event_error_policy=self.process_event_error_policy,
            message_mode=message_mode,
            parse_error_policy=self.parse_error_policy,
            on_connect=self.on_connect,
            on_disconnect=self.on_disconnect,
            on_reconnect=self.on_reconnect,
            reconnect_initial_delay=self.reconnect_initial_delay,
            reconnect_max_delay=self.reconnect_max_delay,
            close_timeout_seconds=self.close_timeout_seconds,
            client_closed_event=self._closed,
            message_queue_maxsize=self.message_queue_maxsize,
            message_queue_overflow_policy=self.sports_message_queue_overflow_policy,
            stale_after_seconds=None,
            respond_to_ping=True,
        )
        return await self._start_background_connection(connection)

    async def close(self) -> None:
        await self._shutdown_connections()

    async def _run_connection(self, connection: _ManagedConnection) -> None:
        await self._register_connection(connection)
        try:
            await connection.run()
        finally:
            await self._unregister_connection(connection)

    async def _start_background_connection[
        TConnection: _ManagedConnection
    ](
        self, connection: TConnection
    ) -> TConnection:
        task = asyncio.create_task(self._run_connection(connection))
        connection.bind_run_task(task)
        try:
            await connection.wait_started()
        except Exception:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            raise
        return connection

    async def _register_connection(self, connection: _ManagedConnection) -> None:
        async with self._connections_lock:
            self._connections.add(connection)

    async def _unregister_connection(self, connection: _ManagedConnection) -> None:
        async with self._connections_lock:
            self._connections.discard(connection)


class _EventLoopThread:
    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._started = threading.Event()
        self._stopping = False
        self._shutdown_lock = threading.Lock()
        self._shutdown_task: asyncio.Task[None] | None = None
        self._thread.start()
        self._started.wait()

    def submit[T](self, coroutine: Coroutine[Any, Any, T]) -> Future[T]:
        if self._stopping:
            coroutine.close()
            msg = "Event loop thread is stopping"
            raise RuntimeError(msg)

        try:
            return asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        except RuntimeError:
            coroutine.close()
            raise

    def stop(self) -> None:
        with self._shutdown_lock:
            if not self._stopping:
                self._stopping = True
                self._loop.call_soon_threadsafe(self._schedule_shutdown)

        self._thread.join(timeout=DEFAULT_LOOP_THREAD_JOIN_TIMEOUT_SECONDS)
        if self._thread.is_alive():
            msg = "Event loop thread failed to stop cleanly"
            raise RuntimeError(msg)

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._started.set()
        try:
            self._loop.run_forever()
        finally:
            pending = [
                task for task in asyncio.all_tasks(self._loop) if not task.done()
            ]
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.close()

    def _schedule_shutdown(self) -> None:
        self._shutdown_task = asyncio.create_task(self._shutdown_loop())

    async def _shutdown_loop(self) -> None:
        current_task = asyncio.current_task()
        tasks = [
            task
            for task in asyncio.all_tasks()
            if task is not current_task and not task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=DEFAULT_LOOP_THREAD_SHUTDOWN_TIMEOUT_SECONDS,
                )
        self._loop.stop()


class SyncRealTimeDataConnection:
    def __init__(
        self,
        *,
        loop_thread: _EventLoopThread,
        handle: AsyncRealTimeDataConnection,
        close_timeout_seconds: float,
    ) -> None:
        self._loop_thread = loop_thread
        self._handle = handle
        self._close_timeout_seconds = close_timeout_seconds

    @property
    def current_subscriptions(self) -> list[dict[str, Any]]:
        future = self._loop_thread.submit(self._handle.get_current_subscriptions())
        return future.result()

    @property
    def last_pong_time(self) -> datetime | None:
        future = self._loop_thread.submit(self._handle.get_health())
        return future.result().last_pong_time

    @property
    def health(self) -> ConnectionHealth:
        future = self._loop_thread.submit(self._handle.get_health())
        return future.result()

    def is_healthy(self, max_silence_seconds: float | None = None) -> bool:
        future = self._loop_thread.submit(
            self._handle.get_is_healthy(max_silence_seconds=max_silence_seconds)
        )
        return future.result()

    def subscribe(self, subscriptions: Sequence[RealTimeDataSubscriptionInput]) -> None:
        future = self._loop_thread.submit(self._handle.subscribe(subscriptions))
        future.result()

    def unsubscribe(self, subscriptions: Sequence[RealTimeDataSubscriptionInput]) -> None:
        future = self._loop_thread.submit(self._handle.unsubscribe(subscriptions))
        future.result()

    def close(self) -> None:
        future = self._loop_thread.submit(self._handle.close())
        future.result(timeout=self._close_timeout_seconds)

    def graceful_close(self) -> None:
        future = self._loop_thread.submit(self._handle.graceful_close())
        future.result(timeout=self._close_timeout_seconds)

    def abort(self) -> None:
        future = self._loop_thread.submit(self._handle.abort())
        future.result(timeout=self._close_timeout_seconds)


class SyncChannelConnection:
    def __init__(
        self,
        *,
        loop_thread: _EventLoopThread,
        handle: AsyncChannelConnection,
        close_timeout_seconds: float,
    ) -> None:
        self._loop_thread = loop_thread
        self._handle = handle
        self._close_timeout_seconds = close_timeout_seconds

    @property
    def last_pong_time(self) -> datetime | None:
        future = self._loop_thread.submit(self._handle.get_health())
        return future.result().last_pong_time

    @property
    def health(self) -> ConnectionHealth:
        future = self._loop_thread.submit(self._handle.get_health())
        return future.result()

    def is_healthy(self, max_silence_seconds: float | None = None) -> bool:
        future = self._loop_thread.submit(
            self._handle.get_is_healthy(max_silence_seconds=max_silence_seconds)
        )
        return future.result()

    @property
    def market_book_synchronized(self) -> bool:
        future = self._loop_thread.submit(self._handle.get_market_book_synchronized())
        return future.result()

    @property
    def last_book_snapshot_time(self) -> datetime | None:
        future = self._loop_thread.submit(self._handle.get_last_book_snapshot_time())
        return future.result()

    @property
    def market_book_invalid_reason(self) -> str | None:
        future = self._loop_thread.submit(self._handle.get_market_book_invalid_reason())
        return future.result()

    @property
    def local_order_books(self) -> LocalOrderBookStore | None:
        return self._handle.local_order_books

    def close(self) -> None:
        future = self._loop_thread.submit(self._handle.close())
        future.result(timeout=self._close_timeout_seconds)

    def graceful_close(self) -> None:
        future = self._loop_thread.submit(self._handle.graceful_close())
        future.result(timeout=self._close_timeout_seconds)

    def abort(self) -> None:
        future = self._loop_thread.submit(self._handle.abort())
        future.result(timeout=self._close_timeout_seconds)

    def wait_closed(self) -> None:
        future = self._loop_thread.submit(self._handle.wait_closed())
        future.result(timeout=self._close_timeout_seconds)


class PolymarketWebsocketsClient:
    """
    Synchronous wrapper around the async websocket client.

    Primary API:
    - open_*_connection(): returns a synchronous connection handle

    Convenience API:
    - run_*_stream(): opens a stream and blocks until it closes
    """

    def __init__(
        self,
        *,
        callbacks: WebsocketCallbackConfig | None = None,
        queue: WebsocketQueueConfig | None = None,
        reconnect: WebsocketReconnectConfig | None = None,
        sync_close_timeout_seconds: float = DEFAULT_SYNC_CLOSE_TIMEOUT_SECONDS,
    ) -> None:
        self._loop_thread = _EventLoopThread()
        self._sync_close_timeout_seconds = sync_close_timeout_seconds
        self._async_client = AsyncPolymarketWebsocketsClient(
            callbacks=callbacks,
            queue=queue,
            reconnect=reconnect,
        )

    @property
    def url_market(self) -> str:
        return self._async_client.url_market

    @url_market.setter
    def url_market(self, value: str) -> None:
        self._async_client.url_market = value

    @property
    def url_user(self) -> str:
        return self._async_client.url_user

    @url_user.setter
    def url_user(self, value: str) -> None:
        self._async_client.url_user = value

    @property
    def url_real_time_data(self) -> str:
        return self._async_client.url_real_time_data

    @url_real_time_data.setter
    def url_real_time_data(self, value: str) -> None:
        self._async_client.url_real_time_data = value

    @property
    def url_sports(self) -> str:
        return self._async_client.url_sports

    @url_sports.setter
    def url_sports(self, value: str) -> None:
        self._async_client.url_sports = value

    def run_market_stream(
        self,
        token_ids: list[str],
        custom_feature_enabled: bool = True,
        process_event: ProcessEventCallback = _default_process_market_event,
        parse_messages: bool = True,
        message_mode: MessageMode | None = None,
        local_order_books: LocalOrderBookStore | None = None,
    ) -> None:
        future = self._loop_thread.submit(
            self._async_client.run_market_stream(
                token_ids=token_ids,
                custom_feature_enabled=custom_feature_enabled,
                process_event=process_event,
                parse_messages=parse_messages,
                message_mode=message_mode,
                local_order_books=local_order_books,
            )
        )
        future.result()

    def open_market_connection(
        self,
        token_ids: list[str],
        custom_feature_enabled: bool = True,
        process_event: ProcessEventCallback = _default_process_market_event,
        parse_messages: bool = True,
        message_mode: MessageMode | None = None,
        local_order_books: LocalOrderBookStore | None = None,
    ) -> SyncChannelConnection:
        future = self._loop_thread.submit(
            self._async_client.open_market_connection(
                token_ids=token_ids,
                custom_feature_enabled=custom_feature_enabled,
                process_event=process_event,
                parse_messages=parse_messages,
                message_mode=message_mode,
                local_order_books=local_order_books,
            )
        )
        handle = future.result()
        return SyncChannelConnection(
            loop_thread=self._loop_thread,
            handle=handle,
            close_timeout_seconds=self._sync_close_timeout_seconds,
        )

    def run_user_stream(
        self,
        creds: ApiCreds,
        condition_ids: list[str] | None = None,
        process_event: ProcessEventCallback = _default_process_user_event,
        parse_messages: bool = True,
        message_mode: MessageMode | None = None,
    ) -> None:
        future = self._loop_thread.submit(
            self._async_client.run_user_stream(
                creds=creds,
                condition_ids=condition_ids,
                process_event=process_event,
                parse_messages=parse_messages,
                message_mode=message_mode,
            )
        )
        future.result()

    def open_user_connection(
        self,
        creds: ApiCreds,
        condition_ids: list[str] | None = None,
        process_event: ProcessEventCallback = _default_process_user_event,
        parse_messages: bool = True,
        message_mode: MessageMode | None = None,
    ) -> SyncChannelConnection:
        future = self._loop_thread.submit(
            self._async_client.open_user_connection(
                creds=creds,
                condition_ids=condition_ids,
                process_event=process_event,
                parse_messages=parse_messages,
                message_mode=message_mode,
            )
        )
        handle = future.result()
        return SyncChannelConnection(
            loop_thread=self._loop_thread,
            handle=handle,
            close_timeout_seconds=self._sync_close_timeout_seconds,
        )

    def open_real_time_data_connection(
        self,
        subscriptions: list[RealTimeDataSubscriptionInput],
        process_event: ProcessEventCallback = _default_process_real_time_data_event,
        parse_messages: bool = True,
        message_mode: MessageMode | None = None,
    ) -> SyncRealTimeDataConnection:
        future = self._loop_thread.submit(
            self._async_client.open_real_time_data_connection(
                subscriptions=subscriptions,
                process_event=process_event,
                parse_messages=parse_messages,
                message_mode=message_mode,
            )
        )
        handle = future.result()
        return SyncRealTimeDataConnection(
            loop_thread=self._loop_thread,
            handle=handle,
            close_timeout_seconds=self._sync_close_timeout_seconds,
        )

    def run_real_time_data_stream(
        self,
        subscriptions: list[RealTimeDataSubscriptionInput],
        process_event: ProcessEventCallback = _default_process_real_time_data_event,
        parse_messages: bool = True,
        message_mode: MessageMode | None = None,
    ) -> None:
        future = self._loop_thread.submit(
            self._async_client.run_real_time_data_stream(
                subscriptions=subscriptions,
                process_event=process_event,
                parse_messages=parse_messages,
                message_mode=message_mode,
            )
        )
        future.result()

    def run_sports_stream(
        self,
        process_event: ProcessEventCallback = _default_process_sports_event,
        parse_messages: bool = True,
        message_mode: MessageMode | None = None,
    ) -> None:
        future = self._loop_thread.submit(
            self._async_client.run_sports_stream(
                process_event=process_event,
                parse_messages=parse_messages,
                message_mode=message_mode,
            )
        )
        future.result()

    def open_sports_connection(
        self,
        process_event: ProcessEventCallback = _default_process_sports_event,
        parse_messages: bool = True,
        message_mode: MessageMode | None = None,
    ) -> SyncChannelConnection:
        future = self._loop_thread.submit(
            self._async_client.open_sports_connection(
                process_event=process_event,
                parse_messages=parse_messages,
                message_mode=message_mode,
            )
        )
        handle = future.result()
        return SyncChannelConnection(
            loop_thread=self._loop_thread,
            handle=handle,
            close_timeout_seconds=self._sync_close_timeout_seconds,
        )

    def close(self) -> None:
        future = self._loop_thread.submit(self._async_client.close())
        future.result(timeout=self._sync_close_timeout_seconds)
        self._loop_thread.stop()
