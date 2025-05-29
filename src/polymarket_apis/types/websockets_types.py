from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional
from datetime import datetime

from ..types.common import Keccak256, EthAddress
from ..types.clob_types import OrderBookSummary, PriceLevel, TickSize, MakerOrder

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
    associated_trades: Optional[list[str]] = None # list of trade ids which
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
    expiration: Optional[datetime] = None
    timestamp: datetime # time of event

    event_type: Literal["order"]
    type: Literal["PLACEMENT", "UPDATE" , "CANCELLATION"]

    status: Literal["LIVE", "CANCELED", "MATCHED"]

    @field_validator('expiration', mode='before')
    def validate_expiration(cls, v):
        if v == '0':
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
    matchtime: Optional[datetime] = None # time trade was matched
    timestamp: datetime # time of event

    event_type: Literal["trade"]
    type: Literal["TRADE"]

    status: Literal["MATCHED", "MINED", "CONFIRMED", "RETRYING", "FAILED"]

# wss://ws-live-data.polymarket.com types
class LiveDataTrade(BaseModel):
    asset: str  # ERC1155 token ID of conditional token being traded
    bio: str  # Bio of the user of the trade
    condition_id: str = Field(alias="conditionId")  # Id of market which is also the CTF condition ID
    event_slug: str = Field(alias="eventSlug")  # Slug of the event
    icon: str  # URL to the market icon image
    name: str  # Name of the user of the trade
    outcome: str  # Human readable outcome of the market
    outcome_index: int = Field(alias="outcomeIndex")  # Index of the outcome
    price: float  # Price of the trade
    profile_image: str = Field(alias="profileImage")  # URL to the user profile image
    profile_image_optimized: str = Field(alias="profileImageOptimized")
    proxy_wallet: str = Field(alias="proxyWallet")  # Address of the user proxy wallet
    pseudonym: str  # Pseudonym of the user
    side: Literal["BUY", "SELL"]  # Side of the trade
    size: float  # Size of the trade
    slug: str  # Slug of the market
    timestamp: int  # Timestamp of the trade
    title: str  # Title of the event
    transaction_hash: str = Field(alias="transactionHash")  # Hash of the transaction

class Comment(BaseModel):
    id: str  # Unique identifier of comment
    body: str  # Content of the comment
    parent_entity_type: str = Field(alias="parentEntityType")  # Type of the parent entity (Event or Series)
    parent_entity_id: int = Field(alias="parentEntityID")  # ID of the parent entity
    parent_comment_id: Optional[str] = Field(None, alias="parentCommentID")  # ID of the parent comment
    user_address: str = Field(alias="userAddress")  # Address of the user
    reply_address: Optional[str] = Field(None, alias="replyAddress")  # Address of the reply user
    created_at: datetime = Field(alias="createdAt")  # Creation timestamp
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")  # Last update timestamp

class Reaction(BaseModel):
    id: str  # Unique identifier of reaction
    comment_id: int = Field(alias="commentID")  # ID of the comment
    reaction_type: str = Field(alias="reactionType")  # Type of the reaction
    icon: Optional[str] = None  # Icon representing the reaction
    user_address: str = Field(alias="userAddress")  # Address of the user
    created_at: datetime = Field(alias="createdAt")  # Creation timestamp

class LiveDataTradeEvent(BaseModel):
    payload: LiveDataTrade
    timestamp: datetime
    type: Literal["trades"]
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

