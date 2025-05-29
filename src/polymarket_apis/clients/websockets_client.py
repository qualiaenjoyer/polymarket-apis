from lomond import WebSocket
from lomond.persist import persist
from typing import Callable, List, Dict, Any

from ..types.websockets_types import (
    OrderBookSummaryEvent,
    PriceChangeEvent,
    TickSizeChangeEvent,
    OrderEvent,
    TradeEvent,
    LiveDataTradeEvent,
    CommentEvent,
    ReactionEvent
)
from ..types.clob_types import ApiCreds

def _process_market_event(event):
    try:
        event = event.json
        for message in event:
            match message["event_type"]:
                case "book":
                    print(OrderBookSummaryEvent(**message), "\n")
                case "price_change":
                    print(PriceChangeEvent(**message), "\n")
                case "tick_size_change":
                    print(TickSizeChangeEvent(**message), "\n")
    except ValueError:
        print(event.text)

def _process_user_event(event):
    try:
        event = event.json
        for message in event:
            match message["event_type"]:
                case "order":
                    print(OrderEvent(**message), "\n")
                case "trade":
                    print(TradeEvent(**message), "\n")
    except ValueError:
        print(event.text)

def _process_live_data_event(event):
    try:
        message = event.json
        match message["type"]:
            case "trades":
                print(LiveDataTradeEvent(**message), "\n")
            case "comment_created" | "comment_removed":
                print(CommentEvent(**message), "\n")
            case "reaction_created" | "reaction_removed":
                print(ReactionEvent(**message), "\n")
    except Exception as e:
        print(e, "\n")
        print(event.text)

class PolymarketWebsocketsClient:
    def __init__(self):
        self.url_market = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        self.url_user = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
        self.url_live_data = "wss://ws-live-data.polymarket.com"

    def market_socket(self, token_ids: List[str], process_event: Callable = _process_market_event):
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
                    auth = creds.model_dump(by_alias=True)
                )
            elif event.name == "text":
                process_event(event)

    def live_data_socket(self, subscriptions: List[Dict[str, Any]], process_event: Callable = _process_live_data_event):
        """
        Connect to the live data websocket and subscribe to specified events.

        Args:
            subscriptions: List of subscription configurations
            process_event: Callback function to process received events
        """
        websocket = WebSocket(self.url_live_data)
        for event in persist(websocket):
            if event.name == "ready":
                websocket.send_json(
                    action="subscribe",
                    subscriptions=subscriptions
                )
            elif event.name == "text":
                process_event(event)
