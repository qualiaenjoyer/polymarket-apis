from datetime import datetime
from typing import Literal, Optional

from pydantic import AliasChoices, BaseModel, Field, field_validator

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


class OrderBookSummaryEvent(OrderBookSummary):
    event_type: Literal["book"]


class PriceChangeEvent(PriceChanges):
    event_type: Literal["price_change"]


class TickSizeChangeEvent(TickSizeChange):
    side: Literal["BUY", "SELL"]
    timestamp: datetime
    event_type: Literal["tick_size_change"]


class LastTradePriceEvent(LastTradePrice):
    timestamp: datetime
    event_type: Literal["last_trade_price"]


# wss://ws-subscriptions-clob.polymarket.com/ws/user types


class OrderEvent(BaseModel):
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
    type: Literal["PLACEMENT", "UPDATE", "CANCELLATION"]

    status: Literal["LIVE", "CANCELED", "MATCHED"]

    @field_validator("expiration", mode="before")
    def validate_expiration(cls, v):
        if v == "0":
            return None
        return v


class TradeEvent(BaseModel):
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


class Request(BaseModel):
    request_id: str = Field(alias="requestId")  # Unique identifier for the request
    proxy_address: str = Field(alias="proxyAddress")  # Proxy address
    user_address: str = Field(alias="userAddress")  # User address
    condition_id: Keccak256 = Field(
        alias="market"
    )  # Id of market which is also the CTF condition ID
    token_id: str = Field(
        alias="token"
    )  # ERC1155 token ID of conditional token being traded
    complement_token_id: str = Field(
        alias="complement"
    )  # Complement ERC1155 token ID of conditional token being traded
    state: Literal[
        "STATE_REQUEST_EXPIRED",
        "STATE_USER_CANCELED",
        "STATE_REQUEST_CANCELED",
        "STATE_MAKER_CANCELED",
        "STATE_ACCEPTING_QUOTES",
        "STATE_REQUEST_QUOTED",
        "STATE_QUOTE_IMPROVED",
    ]  # Current state of the request
    side: Literal["BUY", "SELL"]  # Indicates buy or sell side
    price: float  # Price from in/out sizes
    size_in: float = Field(alias="sizeIn")  # Input size of the request
    size_out: float = Field(alias="sizeOut")  # Output size of the request
    expiry: Optional[datetime] = None


class Quote(BaseModel):
    quote_id: str = Field(alias="quoteId")  # Unique identifier for the quote
    request_id: str = Field(alias="requestId")  # Associated request identifier
    proxy_address: str = Field(alias="proxyAddress")  # Proxy address
    user_address: str = Field(alias="userAddress")  # User address
    condition_id: Keccak256 = Field(
        alias="condition"
    )  # Id of market which is also the CTF condition ID
    token_id: str = Field(
        alias="token"
    )  # ERC1155 token ID of conditional token being traded
    complement_token_id: str = Field(
        alias="complement"
    )  # Complement ERC1155 token ID of conditional token being traded
    state: Literal[
        "STATE_REQUEST_EXPIRED",
        "STATE_USER_CANCELED",
        "STATE_REQUEST_CANCELED",
        "STATE_MAKER_CANCELED",
        "STATE_ACCEPTING_QUOTES",
        "STATE_REQUEST_QUOTED",
        "STATE_QUOTE_IMPROVED",
    ]  # Current state of the quote
    side: Literal["BUY", "SELL"]  # Indicates buy or sell side
    size_in: float = Field(alias="sizeIn")  # Input size of the quote
    size_out: float = Field(alias="sizeOut")  # Output size of the quote
    expiry: Optional[datetime] = None


class CryptoPriceSubscribe(BaseModel):
    data: list[TimeseriesPoint]
    symbol: str


class CryptoPriceUpdate(TimeseriesPoint):
    symbol: str
    full_accuracy_value: str


class AggOrderBookSummary(OrderBookSummary):
    min_order_size: float
    tick_size: TickSize
    neg_risk: bool


class LiveDataClobMarket(BaseModel):
    token_ids: list[str] = Field(alias="asset_ids")
    condition_id: Keccak256 = Field(alias="market")
    min_order_size: float
    tick_size: TickSize
    neg_risk: bool


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


class RequestEvent(BaseModel):
    payload: Request
    timestamp: datetime
    type: Literal[
        "request_created", "request_edited", "request_canceled", "request_expired"
    ]
    topic: Literal["rfq"]


class QuoteEvent(BaseModel):
    payload: Quote
    timestamp: datetime
    type: Literal["quote_created", "quote_edited", "quote_canceled", "quote_expired"]
    topic: Literal["rfq"]


class CryptoPriceUpdateEvent(BaseModel):
    payload: CryptoPriceUpdate
    timestamp: datetime
    connection_id: str
    type: Literal["update"]
    topic: Literal["crypto_prices", "crypto_prices_chainlink"]


class CryptoPriceSubscribeEvent(BaseModel):
    payload: CryptoPriceSubscribe
    timestamp: datetime
    type: Literal["subscribe"]
    topic: Literal["crypto_prices", "crypto_prices_chainlink"]


class LiveDataOrderBookSummaryEvent(BaseModel):
    payload: list[AggOrderBookSummary] | AggOrderBookSummary
    timestamp: datetime
    connection_id: str
    type: Literal["agg_orderbook"]
    topic: Literal["clob_market"]


class LiveDataPriceChangeEvent(BaseModel):
    payload: PriceChanges
    timestamp: datetime
    connection_id: str
    type: Literal["price_change"]
    topic: Literal["clob_market"]


class LiveDataLastTradePriceEvent(BaseModel):
    payload: LastTradePrice
    timestamp: datetime
    connection_id: str
    type: Literal["last_trade_price"]
    topic: Literal["clob_market"]


class LiveDataTickSizeChangeEvent(BaseModel):
    payload: TickSizeChange
    timestamp: datetime
    connection_id: str
    type: Literal["tick_size_change"]
    topic: Literal["clob_market"]


class MarketStatusChangeEvent(BaseModel):
    payload: LiveDataClobMarket
    timestamp: datetime
    connection_id: str
    type: Literal["market_created", "market_resolved"]
    topic: Literal["clob_market"]


class LiveDataOrderEvent(BaseModel):
    payload: OrderEvent
    timestamp: datetime
    connection_id: str
    type: Literal["order"]
    topic: Literal["clob_user"]


class LiveDataTradeEvent(BaseModel):
    payload: TradeEvent
    timestamp: datetime
    connection_id: str
    type: Literal["trade"]
    topic: Literal["clob_user"]


class ErrorEvent(BaseModel):
    message: str
    connection_id: str = Field(alias="connectionId")
    request_id: str = Field(alias="requestId")
