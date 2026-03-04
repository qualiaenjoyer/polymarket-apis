import logging
from collections.abc import Callable
from json import JSONDecodeError
from typing import Any, cast

from lomond import WebSocket
from lomond.events import Text
from lomond.persist import persist
from pydantic import BaseModel, ValidationError

from ..types.clob_types import ApiCreds
from ..types.websockets_types import (
    ActivityOrderMatchEvent,
    ActivityTradeEvent,
    AssetPriceSubscribeEvent,
    AssetPriceUpdateEvent,
    BestBidAskEvent,
    CommentEvent,
    LastTradePriceEvent,
    MarketResolvedEvent,
    NewMarketEvent,
    OrderBookSummaryEvent,
    OrderEvent,
    PriceChangeEvent,
    QuoteEvent,
    ReactionEvent,
    RequestEvent,
    TickSizeChangeEvent,
    TradeEvent,
)

logger = logging.getLogger(__name__)

type MarketEvents = (
    OrderBookSummaryEvent
    | PriceChangeEvent
    | TickSizeChangeEvent
    | LastTradePriceEvent
    | BestBidAskEvent
    | NewMarketEvent
    | MarketResolvedEvent
)

type UserEvents = OrderEvent | TradeEvent

type LiveDataEvents = (
    ActivityTradeEvent
    | ActivityOrderMatchEvent
    | CommentEvent
    | ReactionEvent
    | RequestEvent
    | QuoteEvent
    | AssetPriceSubscribeEvent
    | AssetPriceUpdateEvent
)


def get_market_event_cls(typ: str | None) -> type[MarketEvents] | None:
    match typ:
        case "book":
            return OrderBookSummaryEvent
        case "price_change":
            return PriceChangeEvent
        case "tick_size_change":
            return TickSizeChangeEvent
        case "last_trade_price":
            return LastTradePriceEvent
        case "best_bid_ask":
            return BestBidAskEvent
        case "new_market":
            return NewMarketEvent
        case "market_resolved":
            return MarketResolvedEvent
        case _:
            return None


def get_user_event_cls(typ: str | None) -> type[UserEvents] | None:
    match typ:
        case "order":
            return OrderEvent
        case "trade":
            return TradeEvent
        case _:
            return None


def get_live_data_event_cls(typ: str | None) -> type[LiveDataEvents] | None:
    match typ:
        case "trades":
            return ActivityTradeEvent
        case "orders_matched":
            return ActivityOrderMatchEvent
        case "comment_created" | "comment_removed":
            return CommentEvent
        case "reaction_created" | "reaction_removed":
            return ReactionEvent
        case (
            "request_created"
            | "request_edited"
            | "request_canceled"
            | "request_expired"
        ):
            return RequestEvent
        case "quote_created" | "quote_edited" | "quote_canceled" | "quote_expired":
            return QuoteEvent
        case "subscribe":
            return AssetPriceSubscribeEvent
        case "update":
            return AssetPriceUpdateEvent
        case _:
            return None


def parse_json(event: Text) -> Any | None:
    try:
        return event.json
    except JSONDecodeError:
        logger.warning("Invalid json: %s", event.text)
        return None


def substitute_cls[T: BaseModel](cls: type[T], data: dict[str, Any]) -> T | None:
    try:
        return cls(**data)
    except ValidationError:
        logger.exception("Cannot initiate: %s with %s", cls, data)
        return None


def parse_event[T: BaseModel](
    message: object,
    get_cls: Callable[[str | None], type[T] | None],
    event_type_field: str,
) -> T | None:
    if not isinstance(message, dict):
        logger.warning("Got %s instead of dict", message)
        return None

    typ = message.get(event_type_field)
    cls = get_cls(typ)

    if cls is None:
        logger.warning("Unknown event type: %s", typ)
        return None

    return substitute_cls(cls, message)


def parse_market_event(text: Text) -> MarketEvents | list[OrderBookSummaryEvent] | None:
    message = parse_json(text)
    if isinstance(message, list):
        result: list[OrderBookSummaryEvent] = []
        for item in message:
            obj = substitute_cls(OrderBookSummaryEvent, item)
            if obj is not None:
                result.append(obj)
        return result

    # For some reason mypy cannot deduce its type
    ret = parse_event(message, get_market_event_cls, "event_type")
    return cast("MarketEvents | None", ret)  # pyrefly: ignore[redundant-cast]


def parse_user_event(text: Text) -> UserEvents | None:
    message = parse_json(text)

    # For some reason mypy cannot deduce its type
    ret = parse_event(message, get_user_event_cls, "event_type")
    return cast("UserEvents | None", ret)  # pyrefly: ignore[redundant-cast]


def parse_live_data_event(text: Text) -> LiveDataEvents | None:
    message = parse_json(text)

    # For some reason mypy cannot deduce its type
    ret = parse_event(message, get_live_data_event_cls, "type")
    return cast("LiveDataEvents | None", ret)  # pyrefly: ignore[redundant-cast]


def _default_process_market_event(text: Text) -> None:
    print(parse_market_event(text))


def _default_process_user_event(text: Text) -> None:
    print(parse_user_event(text))


def _default_process_live_data_event(text: Text) -> None:
    print(parse_live_data_event(text))


class PolymarketWebsocketsClient:
    def __init__(self) -> None:
        self.url_market = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        self.url_user = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
        self.url_live_data = "wss://ws-live-data.polymarket.com"

    def market_socket(
        self,
        token_ids: list[str],
        custom_feature_enabled: bool = True,
        process_event: Callable[[Text], None] = _default_process_market_event,
    ) -> None:
        """
        Connect to the market websocket and subscribe to market events for specific token IDs.

        Args:
            token_ids: List of token IDs to subscribe to
            custom_feature_enabled: Enables best_bid_ask, new_market and market_resolved event types
            process_event: Callback function to process received events

        """
        websocket = WebSocket(self.url_market)

        for event in persist(websocket):  # persist automatically reconnects
            if event.name == "ready":
                websocket.send_json(
                    assets_ids=token_ids, custom_feature_enabled=custom_feature_enabled
                )
            elif event.name == "text":
                process_event(cast("Text", event))

    def user_socket(
        self,
        creds: ApiCreds,
        process_event: Callable[[Text], None] = _default_process_user_event,
    ) -> None:
        """
        Connect to the user websocket and subscribe to user events.

        Args:
            creds: API credentials for authentication
            process_event: Callback function to process received events

        """
        websocket = WebSocket(self.url_user)

        for event in persist(websocket):
            if event.name == "ready":
                websocket.send_json(
                    auth=creds.model_dump(by_alias=True),
                )
            elif event.name == "text":
                process_event(cast("Text", event))

    def live_data_socket(
        self,
        subscriptions: list[dict[str, Any]],
        process_event: Callable[[Text], None] = _default_process_live_data_event,
    ) -> None:
        # info on how to subscribe found at https://github.com/Polymarket/real-time-data-client?tab=readme-ov-file#subscribe
        """
        Connect to the live data websocket and subscribe to specified events.

        Args:
            subscriptions: List of subscription configurations
            process_event: Callback function to process received events

        """
        websocket = WebSocket(self.url_live_data)

        for event in persist(websocket):
            if event.name == "ready":
                payload = {
                    "action": "subscribe",
                    "subscriptions": subscriptions,
                }

                websocket.send_json(**payload)

            elif event.name == "text":
                process_event(cast("Text", event))
