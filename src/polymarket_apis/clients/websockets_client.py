import logging
from collections.abc import Callable, Mapping
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
    LiveDataEvents,
    MarketEvents,
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
    UserEvents,
)

logger = logging.getLogger(__name__)


MARKET_EVENT_CLASSES: Mapping[str, type[MarketEvents]] = {
    "book": OrderBookSummaryEvent,
    "price_change": PriceChangeEvent,
    "tick_size_change": TickSizeChangeEvent,
    "last_trade_price": LastTradePriceEvent,
    "best_bid_ask": BestBidAskEvent,
    "new_market": NewMarketEvent,
    "market_resolved": MarketResolvedEvent,
}

USER_EVENT_CLASSES: Mapping[str, type[UserEvents]] = {
    "order": OrderEvent,
    "trade": TradeEvent,
}

LIVE_DATA_EVENT_CLASSES: Mapping[str, type[LiveDataEvents]] = {
    "trades": ActivityTradeEvent,
    "orders_matched": ActivityOrderMatchEvent,
    "comment_created": CommentEvent,
    "comment_removed": CommentEvent,
    "reaction_created": ReactionEvent,
    "reaction_removed": ReactionEvent,
    "request_created": RequestEvent,
    "request_edited": RequestEvent,
    "request_canceled": RequestEvent,
    "request_expired": RequestEvent,
    "quote_created": QuoteEvent,
    "quote_edited": QuoteEvent,
    "quote_canceled": QuoteEvent,
    "quote_expired": QuoteEvent,
    "subscribe": AssetPriceSubscribeEvent,
    "update": AssetPriceUpdateEvent,
}

def parse_json(event: Text) -> object | None:
    if not event.text or event.text.isspace():
        return None
    try:
        return cast("object", event.json)
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
    classes: Mapping[str, type[T]],
    event_type_field: str,
) -> T | None:
    if message is None:
        return None
    if not isinstance(message, dict):
        logger.warning("Got %s instead of dict", message)
        return None

    typ_obj = message.get(event_type_field)
    typ = typ_obj if isinstance(typ_obj, str) else None
    if typ is None:
        logger.warning("Missing or invalid event type field '%s' in message: %s", event_type_field, message)
        return None

    cls = classes.get(typ)
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

    return parse_event(message, MARKET_EVENT_CLASSES, "event_type")


def parse_user_event(text: Text) -> UserEvents | None:
    message = parse_json(text)

    return parse_event(message, USER_EVENT_CLASSES, "event_type")


def parse_live_data_event(text: Text) -> LiveDataEvents | None:
    message = parse_json(text)

    return parse_event(message, LIVE_DATA_EVENT_CLASSES, "type")


def _default_process_market_event(text: Text) -> None:
    ev = parse_market_event(text)
    if ev is not None:
        print(ev, "\n")


def _default_process_user_event(text: Text) -> None:
    ev = parse_user_event(text)
    if ev is not None:
        print(ev, "\n")


def _default_process_live_data_event(text: Text) -> None:
    ev = parse_live_data_event(text)
    if ev is not None:
        print(ev, "\n")


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
