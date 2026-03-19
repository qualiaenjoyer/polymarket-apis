from datetime import UTC, datetime
from typing import Literal, Optional, cast

from pydantic import BaseModel, Field, field_validator, model_validator

from .common import EmptyString, EthAddress, Keccak256

# Type aliases
type ActivityType = Literal[
    "TRADE", "SPLIT", "MERGE", "REDEEM", "REWARD", "CONVERSION", "MAKER_REBATE", "YIELD"
]


class AccountingSnapshotCSVs(BaseModel):
    """Parsed contents of the accounting snapshot ZIP."""

    positions_csv: str
    equity_csv: str


class GQLPosition(BaseModel):
    user: EthAddress
    token_id: str
    complementary_token_id: str
    condition_id: Keccak256
    outcome_index: int
    balance: float

    @model_validator(mode="before")
    def _flatten(cls, values: dict[str, object]) -> dict[str, object]:
        asset = values.get("asset")
        if isinstance(asset, dict):
            if "id" in asset:
                values.setdefault("token_id", asset["id"])
            if "complement" in asset:
                values.setdefault("complementary_token_id", asset["complement"])
            condition = asset.get("condition")
            if isinstance(condition, dict) and "id" in condition:
                values.setdefault("condition_id", condition["id"])
            if "outcomeIndex" in asset:
                values.setdefault("outcome_index", asset["outcomeIndex"])
            values.pop("asset", None)
        return values

    @field_validator("balance", mode="before")
    @classmethod
    def _parse_balance(cls, value: str | float) -> float:
        if isinstance(value, str):
            value = int(value)
        return value / 10**6


class Position(BaseModel):
    # User identification
    proxy_wallet: EthAddress = Field(alias="proxyWallet")

    # Asset information
    token_id: str = Field(alias="asset")
    complementary_token_id: str = Field(alias="oppositeAsset")
    condition_id: Keccak256 = Field(alias="conditionId")
    event_id: int | None = Field(None, alias="eventId")
    outcome: str
    complementary_outcome: str = Field(alias="oppositeOutcome")
    outcome_index: int = Field(alias="outcomeIndex")

    # Position details
    size: float
    avg_price: float = Field(alias="avgPrice")
    current_price: float = Field(alias="curPrice")
    redeemable: bool
    mergeable: bool = False

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
    def handle_empty_end_date(cls, v: datetime | Literal[""]) -> datetime:
        if v == "":
            return datetime(2099, 12, 31, tzinfo=UTC)
        if isinstance(v, datetime):
            return v
        return cast("datetime", v)


class ClosedPosition(BaseModel):
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
    avg_price: float = Field(alias="avgPrice")
    current_price: float = Field(alias="curPrice")
    timestamp: datetime | None = None

    # Financial metrics
    total_bought: float = Field(alias="totalBought")
    realized_pnl: float = Field(alias="realizedPnl")

    # Event information
    title: str
    slug: str
    icon: str
    event_slug: str = Field(alias="eventSlug")
    end_date: datetime = Field(alias="endDate")

    @field_validator("end_date", mode="before")
    def handle_empty_end_date(cls, v: datetime | Literal[""]) -> datetime:
        if v == "":
            return datetime(2099, 12, 31, tzinfo=UTC)
        if isinstance(v, datetime):
            return v
        return cast("datetime", v)


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
    type: ActivityType
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
    verified: bool | None = None


class HolderResponse(BaseModel):
    # Asset information
    token_id: str = Field(alias="token")

    # Holders list
    holders: list[Holder]


class ValueResponse(BaseModel):
    # User identification
    user: EthAddress

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


class UserID(BaseModel):
    id: str
    creator: bool
    mod: bool
    community_mod: Optional[bool] = Field(None, alias="communityMod")


class UserProfile(BaseModel):
    created_at: datetime = Field(alias="createdAt")
    proxy_wallet: EthAddress = Field(alias="proxyWallet")
    profile_image: Optional[str] = Field(None, alias="profileImage")
    display_username_public: bool = Field(alias="displayUsernamePublic")
    bio: Optional[str] = None
    pseudonym: str
    name: Optional[str] = None
    users: Optional[list[UserID]] = None
    x_username: Optional[str] = Field(None, alias="xUsername")
    verified_badge: bool = Field(alias="verifiedBadge")


class LeaderboardUser(BaseModel):
    rank: int
    proxy_wallet: EthAddress = Field(alias="proxyWallet")
    username: str = Field(alias="userName")
    x_username: str = Field(alias="xUsername")
    verified_badge: bool = Field(alias="verifiedBadge")
    vol: float
    pnl: float
    profile_image: str = Field(alias="profileImage")


class BuilderLeaderboardUser(BaseModel):
    date: Optional[datetime] = Field(None, alias="dt")  # period end date
    rank: int
    builder: str
    volume: float
    active_users: int = Field(alias="activeUsers")
    verified: float
    builder_logo: str = Field(alias="builderLogo")


class MarketValue(BaseModel):
    condition_id: Keccak256 = Field(alias="market")
    value: float


class EventLiveVolume(BaseModel):
    total: Optional[float]
    markets: Optional[list[MarketValue]]
