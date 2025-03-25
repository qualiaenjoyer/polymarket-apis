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

    status: Literal["LIVE", "CANCELLED", "MATCHED"]

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
