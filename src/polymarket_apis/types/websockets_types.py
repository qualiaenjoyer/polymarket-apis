from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..types.clob_types import MakerOrder, OrderBookSummary, PriceLevel, TickSize
from ..types.common import EthAddress, Keccak256


# wss://ws-subscriptions-clob.polymarket.com/ws/market types
class OrderBookSummaryEvent(OrderBookSummary):
    event_type: Literal["book"]

class PriceChangeEvent(BaseModel):
    token_id: str = Field(alias="asset_id")
    changes: list[PriceLevel]
    hash: str
    market: str
    timestamp: datetime # time of event
    event_type: Literal["price_change"]

class TickSizeChangeEvent(BaseModel):
    token_id: str = Field(alias="asset_id")
    condition_id: Keccak256 = Field(alias="market")
    old_tick_size: TickSize
    new_tick_size: TickSize
    side: Literal["BUY", "SELL"]
    timestamp: datetime # time of event
    event_type: Literal["tick_size_change"]

# wss://ws-subscriptions-clob.polymarket.com/ws/user types
class OrderEvent(BaseModel):
    token_id: str = Field(alias="asset_id")
    condition_id: Keccak256 = Field(alias="market")
    order_id: Keccak256 = Field(alias="id")
    associated_trades: list[str] | None = None # list of trade ids which
    maker_address: EthAddress
    order_owner: str # api key of order owner
    event_owner: str = Field(alias="owner") # api key of event owner


    price: float
    side: Literal["BUY", "SELL"]
    size_matched: float
    original_size: float
    outcome: str
    order_type: Literal["GTC", "FOK", "GTD"]

    created_at: datetime
    expiration: datetime | None = None
    timestamp: datetime # time of event

    event_type: Literal["order"]
    type: Literal["PLACEMENT", "UPDATE" , "CANCELLATION"]

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
    trade_owner: str # api key of trade owner
    event_owner: str = Field(alias="owner") # api key of event owner

    price: float
    size: float
    side: Literal["BUY", "SELL"]
    outcome: str

    last_update: datetime # time of last update to trade
    matchtime: datetime | None = None # time trade was matched
    timestamp: datetime # time of event

    event_type: Literal["trade"]
    type: Literal["TRADE"]

    status: Literal["MATCHED", "MINED", "CONFIRMED", "RETRYING", "FAILED"]

# wss://ws-live-data.polymarket.com types
class LiveDataTrade(BaseModel):
    token_id: str = Field(alias="asset") # ERC1155 token ID of conditional token being traded
    condition_id: str = Field(alias="conditionId")  # Id of market which is also the CTF condition ID
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
    profile_image_optimized: str | None = Field(None, alias="profileImageOptimized")


class Comment(BaseModel):
    id: str  # Unique identifier of comment
    body: str  # Content of the comment
    parent_entity_type: str = Field(alias="parentEntityType")  # Type of the parent entity (Event or Series)
    parent_entity_id: int = Field(alias="parentEntityID")  # ID of the parent entity
    parent_comment_id: str | None = Field(None, alias="parentCommentID")  # ID of the parent comment
    user_address: str = Field(alias="userAddress")  # Address of the user
    reply_address: str | None = Field(None, alias="replyAddress")  # Address of the reply user
    created_at: datetime = Field(alias="createdAt")  # Creation timestamp
    updated_at: datetime | None = Field(None, alias="updatedAt")  # Last update timestamp

class Reaction(BaseModel):
    id: str  # Unique identifier of reaction
    comment_id: int = Field(alias="commentID")  # ID of the comment
    reaction_type: str = Field(alias="reactionType")  # Type of the reaction
    icon: str | None = None  # Icon representing the reaction
    user_address: str = Field(alias="userAddress")  # Address of the user
    created_at: datetime = Field(alias="createdAt")  # Creation timestamp

class Request(BaseModel):
    request_id: str = Field(alias="requestId")  # Unique identifier for the request
    proxy_address: str = Field(alias="proxyAddress")  # Proxy address
    user_address: str = Field(alias="userAddress")  # User address
    condition_id: Keccak256 = Field(alias="market")  # Id of market which is also the CTF condition ID
    token_id: str = Field(alias="token")  # ERC1155 token ID of conditional token being traded
    complement_token_id: str = Field(alias="complement")  # Complement ERC1155 token ID of conditional token being traded
    state: Literal["STATE_REQUEST_EXPIRED", "STATE_USER_CANCELED", "STATE_REQUEST_CANCELED", "STATE_MAKER_CANCELED", "STATE_ACCEPTING_QUOTES", "STATE_REQUEST_QUOTED", "STATE_QUOTE_IMPROVED"]  # Current state of the request
    side: Literal["BUY", "SELL"]  # Indicates buy or sell side
    price: float  # Price from in/out sizes
    size_in: float = Field(alias="sizeIn")  # Input size of the request
    size_out: float = Field(alias="sizeOut")  # Output size of the request
    expiry: datetime | None = None

class Quote(BaseModel):
    quote_id: str = Field(alias="quoteId")  # Unique identifier for the quote
    request_id: str = Field(alias="requestId")  # Associated request identifier
    proxy_address: str = Field(alias="proxyAddress")  # Proxy address
    user_address: str = Field(alias="userAddress")  # User address
    condition_id: Keccak256 = Field(alias="condition")  # Id of market which is also the CTF condition ID
    token_id: str = Field(alias="token")  # ERC1155 token ID of conditional token being traded
    complement_token_id: str = Field(alias="complement")  # Complement ERC1155 token ID of conditional token being traded
    state: Literal["STATE_REQUEST_EXPIRED", "STATE_USER_CANCELED", "STATE_REQUEST_CANCELED", "STATE_MAKER_CANCELED", "STATE_ACCEPTING_QUOTES", "STATE_REQUEST_QUOTED", "STATE_QUOTE_IMPROVED"]  # Current state of the quote
    side: Literal["BUY", "SELL"]  # Indicates buy or sell side
    size_in: float = Field(alias="sizeIn")  # Input size of the quote
    size_out: float = Field(alias="sizeOut")  # Output size of the quote
    expiry: datetime | None = None

class LiveDataTradeEvent(BaseModel):
    payload: LiveDataTrade
    timestamp: datetime
    type: Literal["trades"]
    topic: Literal["activity"]

class LiveDataOrderMatchEvent(BaseModel):
    payload: LiveDataTrade
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
    type: Literal["request_created", "request_edited", "request_canceled", "request_expired"]
    topic: Literal["rfq"]

class QuoteEvent(BaseModel):
    payload: Quote
    timestamp: datetime
    type: Literal["quote_created", "quote_edited", "quote_canceled", "quote_expired"]
    topic: Literal["rfq"]
