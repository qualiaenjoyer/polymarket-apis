import json
from datetime import datetime
from typing import Literal, Optional, cast

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)

from ..types.clob_types import MakerOrder, OrderBookSummary, TickSize
from ..types.common import EthAddress, Keccak256, TimeseriesPoint
from ..types.gamma_types import Comment, Reaction

# wss://ws-subscriptions-clob.polymarket.com/ws/market types


class PriceChange(BaseModel):
    best_ask: float = Field(validation_alias=AliasChoices("ba", "best_ask"))
    best_bid: float = Field(validation_alias=AliasChoices("bb", "best_bid"))
    price: float = Field(validation_alias=AliasChoices("p", "price"))
    size: float = Field(validation_alias=AliasChoices("s", "size"))
    side: Literal["BUY", "SELL"] = Field(validation_alias=AliasChoices("si", "side"))
    token_id: str = Field(validation_alias=AliasChoices("a", "asset_id"))
    hash: str = Field(validation_alias=AliasChoices("h", "hash"))


class PriceChanges(BaseModel):
    condition_id: Keccak256 = Field(validation_alias=AliasChoices("m", "market"))
    price_changes: list[PriceChange] = Field(
        validation_alias=AliasChoices("pc", "price_changes")
    )
    timestamp: datetime = Field(validation_alias=AliasChoices("t", "timestamp"))


class TickSizeChange(BaseModel):
    token_id: str = Field(alias="asset_id")
    condition_id: Keccak256 = Field(alias="market")
    old_tick_size: TickSize
    new_tick_size: TickSize


class LastTradePrice(BaseModel):
    price: float
    size: float
    side: Literal["BUY", "SELL"]
    token_id: str = Field(alias="asset_id")
    condition_id: Keccak256 = Field(alias="market")
    fee_rate_bps: float
    transaction_hash: Keccak256 | None = Field(default=None)


class OrderBookSummaryEvent(OrderBookSummary):
    event_type: Literal["book"]


class PriceChangeEvent(PriceChanges):
    event_type: Literal["price_change"]


class TickSizeChangeEvent(TickSizeChange):
    timestamp: datetime
    event_type: Literal["tick_size_change"]


class LastTradePriceEvent(LastTradePrice):
    timestamp: datetime
    event_type: Literal["last_trade_price"]


class BestBidAskEvent(BaseModel):
    condition_id: Keccak256 = Field(alias="market")
    token_id: str = Field(alias="asset_id")
    best_bid: float
    best_ask: float
    spread: float
    timestamp: datetime
    event_type: Literal["best_bid_ask"]


class RelatedEvent(BaseModel):
    id: int
    ticker: str
    slug: str
    title: str
    description: str


class MarketEvent(BaseModel):
    id: int
    question: str
    condition_id: Keccak256 = Field(alias="market")
    slug: str
    description: str
    token_ids: list[str] = Field(alias="assets_ids")
    outcomes: list[str]
    event_info: RelatedEvent = Field(alias="event_message")
    timestamp: datetime
    tags: Optional[list[str]] = None


class NewMarketEvent(MarketEvent):
    event_type: Literal["new_market"]


class MarketResolvedEvent(MarketEvent):
    winning_asset_id: str
    winning_outcome: str
    event_type: Literal["market_resolved"]


# wss://ws-subscriptions-clob.polymarket.com/ws/user types


class OrderEvent(BaseModel):  # type: ignore[no-redef] # event_owner is the same as order_owner
    token_id: str = Field(alias="asset_id")
    condition_id: Keccak256 = Field(alias="market")
    order_id: Keccak256 = Field(alias="id")
    associated_trades: Optional[list[str]] = None  # list of trade ids which
    maker_address: EthAddress
    order_owner: str = Field(alias="owner")  # api key of order owner
    event_owner: Optional[str] = Field(None, alias="owner")  # api key of event owner

    price: float
    side: Literal["BUY", "SELL"]
    size_matched: float
    original_size: float
    outcome: str
    order_type: Literal["GTC", "GTD", "FOK", "FAK"]

    created_at: datetime
    expiration: Optional[datetime] = None
    timestamp: Optional[datetime] = None  # time of event

    event_type: Optional[Literal["order"]] = None
    exchange_version: Optional[str] = None
    type: Literal["PLACEMENT", "UPDATE", "CANCELLATION"]

    status: Literal["LIVE", "CANCELED", "MATCHED"]

    @field_validator("expiration", mode="before")
    def validate_expiration(
        cls, v: Optional[datetime] | Literal["0"]
    ) -> Optional[datetime]:
        if v == "0":
            return None
        if isinstance(v, datetime):
            return v
        return cast("Optional[datetime]", v)


class TradeEvent(BaseModel):  # type: ignore[no-redef] # event_owner is the same as order_owner
    token_id: str = Field(alias="asset_id")
    condition_id: Keccak256 = Field(alias="market")
    taker_order_id: Keccak256
    maker_orders: list[MakerOrder]
    trade_id: str = Field(alias="id")
    trade_owner: Optional[str] = Field(None, alias="owner")  # api key of trade owner
    event_owner: str = Field(alias="owner")  # api key of event owner

    price: float
    size: float
    side: Literal["BUY", "SELL"]
    outcome: str

    last_update: datetime  # time of last update to trade
    matchtime: Optional[datetime] = None  # time trade was matched
    timestamp: Optional[datetime] = None  # time of event

    event_type: Optional[Literal["trade"]] = None
    exchange_version: Optional[str] = None
    type: Optional[Literal["TRADE"]] = None

    status: Literal["MATCHED", "MINED", "CONFIRMED", "RETRYING", "FAILED"]


# wss://ws-live-data.polymarket.com types


# Payload models
class ActivityTrade(BaseModel):
    token_id: str = Field(
        alias="asset"
    )  # ERC1155 token ID of conditional token being traded
    condition_id: str = Field(
        alias="conditionId"
    )  # Id of market which is also the CTF condition ID
    event_slug: str = Field(alias="eventSlug")  # Slug of the event
    outcome: str  # Human readable outcome of the market
    outcome_index: int = Field(alias="outcomeIndex")  # Index of the outcome
    price: float  # Price of the trade
    side: Literal["BUY", "SELL"]  # Side of the trade
    size: float  # Size of the trade
    slug: str  # Slug of the market
    timestamp: datetime  # Timestamp of the trade
    title: str  # Title of the event
    transaction_hash: str = Field(alias="transactionHash")  # Hash of the transaction
    proxy_wallet: str = Field(alias="proxyWallet")  # Address of the user proxy wallet
    icon: str  # URL to the market icon image
    name: str  # Name of the user of the trade
    bio: str  # Bio of the user of the trade
    pseudonym: str  # Pseudonym of the user
    profile_image: str = Field(alias="profileImage")  # URL to the user profile image
    profile_image_optimized: Optional[str] = Field(None, alias="profileImageOptimized")


class AssetPriceSubscribe(BaseModel):
    data: list[TimeseriesPoint]
    symbol: str


class AssetPriceUpdate(TimeseriesPoint):
    symbol: str
    full_accuracy_value: str


class RealTimeDataClobMarket(BaseModel):
    token_ids: list[str] = Field(alias="asset_ids")
    condition_id: Keccak256 = Field(alias="market")
    min_order_size: float
    tick_size: TickSize
    neg_risk: bool


REAL_TIME_DATA_SUBSCRIPTION_TYPES: dict[str, set[str]] = {
    "comments": {
        "*",
        "comment_created",
        "comment_removed",
        "reaction_created",
        "reaction_removed",
    },
    "crypto_prices": {"*", "update"},
    "crypto_prices_chainlink": {"*", "update"},
    "equity_prices": {"*", "update"},
    "activity": {"*", "trades", "orders_matched"},
}


class RealTimeDataGammaAuth(BaseModel):
    address: str


class RealTimeDataSubscription(BaseModel):
    topic: Literal[
        "comments",
        "crypto_prices",
        "crypto_prices_chainlink",
        "equity_prices",
        "activity",
    ]
    type: str
    filters: Optional[str] = None
    gamma_auth: Optional[RealTimeDataGammaAuth] = None

    @field_validator("type")
    def validate_topic_type_pair(
        cls, subscription_type: str, info: ValidationInfo
    ) -> str:
        topic_obj = info.data.get("topic")
        topic = topic_obj if isinstance(topic_obj, str) else None

        if topic is None:
            return subscription_type

        allowed_types = REAL_TIME_DATA_SUBSCRIPTION_TYPES.get(topic)
        if allowed_types is None or subscription_type not in allowed_types:
            msg = (
                "Invalid live data subscription: "
                f"{{'topic': {topic!r}, 'type': {subscription_type!r}}}"
            )
            raise ValueError(msg)
        return subscription_type

    def expand(self) -> list["RealTimeDataSubscription"]:
        if self.type != "*":
            return [self]

        concrete_types = sorted(
            subscription_type
            for subscription_type in REAL_TIME_DATA_SUBSCRIPTION_TYPES[self.topic]
            if subscription_type != "*"
        )
        if not concrete_types:
            return [self]

        return [
            self.model_copy(update={"type": subscription_type})
            for subscription_type in concrete_types
        ]

    def matches_unsubscribe_request(
        self, unsubscribe_request: "RealTimeDataSubscription"
    ) -> bool:
        if self.topic != unsubscribe_request.topic:
            return False
        if unsubscribe_request.type not in {"*", self.type}:
            return False
        if unsubscribe_request.filters is None:
            return True
        return self.filters == unsubscribe_request.filters

    def cache_key(self) -> str:
        payload = self.model_dump(mode="json", by_alias=True, exclude_none=True)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def to_wire_dict(self) -> dict[str, object]:
        return cast(
            "dict[str, object]",
            self.model_dump(mode="json", by_alias=True, exclude_none=True),
        )


# Event models
class ActivityTradeEvent(BaseModel):
    payload: ActivityTrade
    timestamp: datetime
    type: Literal["trades"]
    topic: Literal["activity"]


class ActivityOrderMatchEvent(BaseModel):
    payload: ActivityTrade
    timestamp: datetime
    type: Literal["orders_matched"]
    topic: Literal["activity"]


class CommentEvent(BaseModel):
    payload: Comment
    timestamp: datetime
    type: Literal["comment_created", "comment_removed"]
    topic: Literal["comments"]


class ReactionEvent(BaseModel):
    payload: Reaction
    timestamp: datetime
    type: Literal["reaction_created", "reaction_removed"]
    topic: Literal["comments"]


class AssetPriceUpdateEvent(BaseModel):
    payload: AssetPriceUpdate
    timestamp: datetime
    connection_id: str
    type: Literal["update"]
    topic: Literal["crypto_prices", "crypto_prices_chainlink", "equity_prices"]


class AssetPriceSubscribeEvent(BaseModel):
    payload: AssetPriceSubscribe
    timestamp: datetime
    type: Literal["subscribe"]
    topic: Literal["crypto_prices", "crypto_prices_chainlink", "equity_prices"]


class ScoreStateFields(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    score: str
    period: str
    live: bool
    ended: bool
    elapsed: Optional[str] = None
    finished_timestamp: Optional[datetime] = Field(None, alias="finishedTimestamp")


class SportsEventState(ScoreStateFields):
    type: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class SportsGameUpdate(ScoreStateFields):
    game_id: Optional[int] = Field(None, alias="gameId")
    metadata_game_id: Optional[str] = Field(None, alias="metadataGameId")
    league_abbreviation: str = Field(alias="leagueAbbreviation")

    home_team: Optional[str] = Field(None, alias="homeTeam")
    away_team: Optional[str] = Field(None, alias="awayTeam")
    status: Optional[str] = (
        None  # Literal["InProgress", "Break", "Final", "finished", "running"]
    )

    updated_at: Optional[datetime] = Field(None, alias="updatedAt")
    event_state: Optional[SportsEventState] = Field(None, alias="eventState")


class ErrorEvent(BaseModel):
    message: str
    connection_id: str = Field(alias="connectionId")
    request_id: str = Field(alias="requestId")


# event type unions
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

type RealTimeDataEvents = (
    ActivityTradeEvent
    | ActivityOrderMatchEvent
    | CommentEvent
    | ReactionEvent
    | AssetPriceSubscribeEvent
    | AssetPriceUpdateEvent
)
