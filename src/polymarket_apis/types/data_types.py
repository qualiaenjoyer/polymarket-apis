from datetime import UTC, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .common import EmptyString, EthAddress, Keccak256


class Position(BaseModel):
    # User identification
    proxy_wallet: EthAddress = Field(alias="proxyWallet")

    # Asset information
    token_id: str = Field(alias="asset")
    complementary_token_id: str = Field(alias="oppositeAsset")
    condition_id: Keccak256 = Field(alias="conditionId")
    outcome: str
    complementary_outcome: str = Field(alias="oppositeOutcome")
    outcome_index: int = Field(alias="outcomeIndex")

    # Position details
    size: float
    avg_price: float = Field(alias="avgPrice")
    current_price: float = Field(alias="curPrice")
    redeemable: bool

    # Financial metrics
    initial_value: float = Field(alias="initialValue")
    current_value: float = Field(alias="currentValue")
    cash_pnl: float = Field(alias="cashPnl")
    percent_pnl: float = Field(alias="percentPnl")
    total_bought: float = Field(alias="totalBought")
    realized_pnl: float = Field(alias="realizedPnl")
    percent_realized_pnl: float = Field(alias="percentRealizedPnl")

    # Event information
    title: str
    slug: str
    icon: str
    event_slug: str = Field(alias="eventSlug")
    end_date: datetime = Field(alias="endDate")
    negative_risk: bool = Field(alias="negativeRisk")

    @field_validator("end_date", mode="before")
    def handle_empty_end_date(cls, v):
        if v == "":
            return datetime(2099, 12, 31, tzinfo=UTC)
        return v


class Trade(BaseModel):
    # User identification
    proxy_wallet: EthAddress = Field(alias="proxyWallet")

    # Trade details
    side: Literal["BUY", "SELL"]
    token_id: str = Field(alias="asset")
    condition_id: Keccak256 = Field(alias="conditionId")
    size: float
    price: float
    timestamp: datetime

    # Event information
    title: str
    slug: str
    icon: str
    event_slug: str = Field(alias="eventSlug")
    outcome: str
    outcome_index: int = Field(alias="outcomeIndex")

    # User profile
    name: str
    pseudonym: str
    bio: str
    profile_image: str = Field(alias="profileImage")
    profile_image_optimized: str = Field(alias="profileImageOptimized")

    # Transaction information
    transaction_hash: Keccak256 = Field(alias="transactionHash")


class Activity(BaseModel):
    # User identification
    proxy_wallet: EthAddress = Field(alias="proxyWallet")

    # Activity details
    timestamp: datetime
    condition_id: Keccak256 | EmptyString = Field(alias="conditionId")
    type: Literal["TRADE", "SPLIT", "MERGE", "REDEEM", "REWARD", "CONVERSION"]
    size: float
    usdc_size: float = Field(alias="usdcSize")
    price: float
    asset: str
    side: str | None
    outcome_index: int = Field(alias="outcomeIndex")

    # Event information
    title: str
    slug: str
    icon: str
    event_slug: str = Field(alias="eventSlug")
    outcome: str

    # User profile
    name: str
    pseudonym: str
    bio: str
    profile_image: str = Field(alias="profileImage")
    profile_image_optimized: str = Field(alias="profileImageOptimized")

    # Transaction information
    transaction_hash: Keccak256 = Field(alias="transactionHash")


class Holder(BaseModel):
    # User identification
    proxy_wallet: EthAddress = Field(alias="proxyWallet")

    # Holder details
    token_id: str = Field(alias="asset")
    amount: float
    outcome_index: int = Field(alias="outcomeIndex")

    # User profile
    name: str
    pseudonym: str
    bio: str
    profile_image: str = Field(alias="profileImage")
    profile_image_optimized: str = Field(alias="profileImageOptimized")
    display_username_public: bool = Field(alias="displayUsernamePublic")


class HolderResponse(BaseModel):
    # Asset information
    token_id: str = Field(alias="token")

    # Holders list
    holders: list[Holder]


class ValueResponse(BaseModel):
    # User identification
    proxy_wallet: EthAddress = Field(alias="proxyWallet")

    # Value information
    value: float


class User(BaseModel):
    proxy_wallet: EthAddress = Field(alias="proxyWallet")
    name: str
    bio: str
    profile_image: str = Field(alias="profileImage")
    profile_image_optimized: str = Field(alias="profileImageOptimized")


class UserMetric(User):
    amount: float
    pseudonym: str


class UserRank(User):
    amount: float
    rank: int


class MarketValue(BaseModel):
    condition_id: Keccak256 = Field(alias="market")
    value: float


class EventLiveVolume(BaseModel):
    total: Optional[float]
    markets: Optional[list[MarketValue]]
