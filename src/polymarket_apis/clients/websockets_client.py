from collections.abc import Callable
from json import JSONDecodeError
from typing import Any, Optional

from lomond import WebSocket
from lomond.persist import persist
from pydantic import ValidationError

from ..types.clob_types import ApiCreds
from ..types.websockets_types import (
    ActivityOrderMatchEvent,
    ActivityTradeEvent,
    CommentEvent,
    CryptoPriceSubscribeEvent,
    CryptoPriceUpdateEvent,
    LastTradePriceEvent,
    LiveDataLastTradePriceEvent,
    LiveDataOrderBookSummaryEvent,
    LiveDataOrderEvent,
    LiveDataPriceChangeEvent,
    LiveDataTickSizeChangeEvent,
    LiveDataTradeEvent,
    MarketStatusChangeEvent,
    OrderBookSummaryEvent,
    OrderEvent,
    PriceChangeEvent,
    QuoteEvent,
    ReactionEvent,
    RequestEvent,
    TickSizeChangeEvent,
    TradeEvent,
)
from ..utilities.exceptions import AuthenticationRequiredError


def _process_market_event(event):
    try:
        message = event.json
        if isinstance(message, list):
            for item in message:
                try:
                    print(OrderBookSummaryEvent(**item), "\n")
                except ValidationError as e:
                    print(item.text)
                    print(e.errors())
            return
        match message["event_type"]:
            case "book":
                print(OrderBookSummaryEvent(**message), "\n")
            case "price_change":
                print(PriceChangeEvent(**message), "\n")
            case "tick_size_change":
                print(TickSizeChangeEvent(**message), "\n")
            case "last_trade_price":
                print(LastTradePriceEvent(**message), "\n")
            case _:
                print(message)
    except JSONDecodeError:
        print(event.text)
    except ValidationError as e:
        print(e.errors())
        print(event.json)

def _process_user_event(event):
    try:
        message = event.json
        match message["event_type"]:
            case "order":
                print(OrderEvent(**message), "\n")
            case "trade":
                print(TradeEvent(**message), "\n")
    except JSONDecodeError:
        print(event.text)
    except ValidationError as e:
        print(event.text)
        print(e.errors(), "\n")

def _process_live_data_event(event):
    try:
        message = event.json
        match message["type"]:
            case "trades":
                print(ActivityTradeEvent(**message), "\n")
            case "orders_matched":
                print(ActivityOrderMatchEvent(**message), "\n")
            case "comment_created" | "comment_removed":
                print(CommentEvent(**message), "\n")
            case "reaction_created" | "reaction_removed":
                print(ReactionEvent(**message), "\n")
            case "request_created" | "request_edited" | "request_canceled" | "request_expired":
                print(RequestEvent(**message), "\n")
            case "quote_created" | "quote_edited" | "quote_canceled" | "quote_expired":
                print(QuoteEvent(**message), "\n")
            case "subscribe":
                print(CryptoPriceSubscribeEvent(**message), "\n")
            case "update":
                print(CryptoPriceUpdateEvent(**message), "\n")
            case "agg_orderbook":
                print(LiveDataOrderBookSummaryEvent(**message), "\n")
            case "price_change":
                print(LiveDataPriceChangeEvent(**message), "\n")
            case "last_trade_price":
                print(LiveDataLastTradePriceEvent(**message), "\n")
            case "tick_size_change":
                print(LiveDataTickSizeChangeEvent(**message), "\n")
            case "market_created" | "market_resolved":
                print(MarketStatusChangeEvent(**message), "\n")
            case "order":
                print(LiveDataOrderEvent(**message), "\n")
            case "trade":
                print(LiveDataTradeEvent(**message), "\n")
            case _:
                print(message)
    except JSONDecodeError:
        print(event.text)
    except ValidationError as e:
        print(e.errors(), "\n")
        print(event.text)

class PolymarketWebsocketsClient:
    def __init__(self):
        self.url_market = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        self.url_user = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
        self.url_live_data = "wss://ws-live-data.polymarket.com"

    def market_socket(self, token_ids: list[str], process_event: Callable = _process_market_event):
        """
        Connect to the market websocket and subscribe to market events for specific token IDs.

        Args:
            token_ids: List of token IDs to subscribe to
            process_event: Callback function to process received events

        """
        websocket = WebSocket(self.url_market)

        for event in persist(websocket):  # persist automatically reconnects
            if event.name == "ready":
                websocket.send_json(
                    assets_ids=token_ids,
                )
            elif event.name == "text":
                process_event(event)

    def user_socket(self, creds: ApiCreds, process_event: Callable = _process_user_event):
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
                process_event(event)

    def live_data_socket(self, subscriptions: list[dict[str, Any]], process_event: Callable = _process_live_data_event, creds: Optional[ApiCreds] = None):
        # info on how to subscribe found at https://github.com/Polymarket/real-time-data-client?tab=readme-ov-file#subscribe
        """
        Connect to the live data websocket and subscribe to specified events.

        Args:
            subscriptions: List of subscription configurations
            process_event: Callback function to process received events
            creds: ApiCreds for authentication if subscribing to clob_user topic

        """
        websocket = WebSocket(self.url_live_data)

        needs_auth = any(sub.get("topic") == "clob_user" for sub in subscriptions)
        if needs_auth and creds is None:
            msg = "ApiCreds credentials are required for the clob_user topic subscriptions"
            raise AuthenticationRequiredError(msg)

        for event in persist(websocket):
            if event.name == "ready":
                if needs_auth:
                    subscriptions_with_creds = []
                    for sub in subscriptions:
                        if sub.get("topic") == "clob_user":
                            sub_copy = sub.copy()
                            sub_copy["clob_auth"] = creds.model_dump()
                            subscriptions_with_creds.append(sub_copy)
                        else:
                            subscriptions_with_creds.append(sub)
                    subscriptions = subscriptions_with_creds

                payload = {
                    "action": "subscribe",
                    "subscriptions": subscriptions,
                }

                websocket.send_json(**payload)

            elif event.name == "text":
                process_event(event)
