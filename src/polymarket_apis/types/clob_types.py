from enum import Enum
from typing import Any, Literal, Optional, Dict, TypeVar, Generic

from pydantic import (
    BaseModel,
    RootModel,
    Field,
    field_validator,
    field_serializer,
    ValidationInfo,
    ValidatorFunctionWrapHandler,

)
from ..utilities.constants import ZERO_ADDRESS
from ..types.common import Keccak256, EthAddress


from datetime import datetime

# TODO check types


class ApiCreds(BaseModel):
    api_key: str = Field(alias="apiKey")
    secret: str
    passphrase: str


class RequestArgs(BaseModel):
    method: Literal["GET", "POST", "DELETE"]
    request_path: str
    body: Optional[Any] = None


class TokenValue(BaseModel):
    token_id: str
    value: float


class Midpoint(TokenValue):
    pass


class Spread(TokenValue):
    pass


class TokenValueDict(RootModel):
    root: Dict[str, float]


class BookParams(BaseModel):
    token_id: str
    side: Literal["BUY", "SELL"]


class Price(BookParams):
    price: float


class BidAsk(BaseModel):
    BUY: Optional[float] = None  # Price buyers are willing to pay
    SELL: Optional[float] = None  # Price sellers are willing to accept


class TokenBidAsk(BidAsk):
    token_id: str


class TokenBidAskDict(RootModel):
    root: Dict[str, BidAsk]


class Token(BaseModel):
    token_id: str
    outcome: str
    price: float
    winner: Optional[bool] = None


class TimeseriesPoint(BaseModel):
    t: datetime
    p: float


class PriceHistory(BaseModel):
    token_id: str
    history: list[TimeseriesPoint]


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    next_cursor: str
    limit: int
    count: int


class RewardRate(BaseModel):
    asset_address: str
    rewards_daily_rate: float


class RewardConfig(BaseModel):
    asset_address: str
    rewards_daily_rate: float = Field(alias="rate_per_day")

    start_date: datetime
    end_date: datetime

    reward_id: Optional[str] = Field(None, alias="id")
    total_rewards: float
    total_days: Optional[int] = None

    @field_validator('reward_id', mode='before')
    def convert_id_to_str(cls, v):
        if isinstance(v, int):
            return str(v)
        return v


class Rewards(BaseModel):
    rates: Optional[list[RewardRate]]
    rewards_min_size: int = Field(alias="min_size")
    rewards_max_spread: float = Field(alias="max_spread")

class EarnedReward(BaseModel):
    asset_address: EthAddress
    earnings: float
    asset_rate: float

class DailyEarnedReward(BaseModel):
    date: datetime
    asset_address: EthAddress
    maker_address: EthAddress
    earnings: float
    asset_rate: float

class PolymarketRewardItem(BaseModel):
    market_id: str
    condition_id: Keccak256
    question: str
    market_slug: str
    market_description: str
    event_slug: str
    image: str
    maker_address: EthAddress
    tokens: list[Token]
    rewards_config: list[RewardConfig]
    earnings: list[EarnedReward]
    rewards_max_spread: float
    rewards_min_size: float
    earning_percentage: float
    spread: float
    market_competitiveness: float


class RewardsMarket(BaseModel):
    condition_id: Keccak256
    question: str
    market_slug: str
    event_slug: str
    image: str
    tokens: list[Token]
    rewards_config: list[RewardConfig]
    rewards_max_spread: float
    rewards_min_size: int
    market_competitiveness: float

class ClobMarket(BaseModel):
    # Order book settings
    enable_order_book: bool
    accepting_orders: bool
    accepting_order_timestamp: Optional[datetime]
    minimum_order_size: float
    minimum_tick_size: float

    # Core market information
    condition_id: Keccak256
    question_id: Keccak256
    question: str
    description: str
    market_slug: str
    end_date_iso: Optional[datetime]
    game_start_time: Optional[datetime] = None
    seconds_delay: int

    # Status flags
    active: bool
    closed: bool
    archived: bool

    # Fee structure
    fpmm: str
    maker_base_fee: float
    taker_base_fee: float

    # Features
    notifications_enabled: bool
    is_50_50_outcome: bool

    # Negative risk settings
    neg_risk: bool
    neg_risk_market_id: Keccak256
    neg_risk_request_id: Keccak256

    # Visual representation
    icon: str
    image: str

    # Rewards configuration
    rewards: Optional[Rewards]

    # Token information
    tokens: list[Token]

    # Tags
    tags: Optional[list[str]]

    @field_validator("neg_risk_market_id", "neg_risk_request_id", mode="wrap")
    @classmethod
    def validate_neg_risk_fields(
            cls, value: str, handler: ValidatorFunctionWrapHandler, info: ValidationInfo
    ) -> str:
        try:
            # First attempt standard validation
            return handler(value)
        except ValueError as original_error:
            neg_risk = info.data.get("neg_risk", False)

            # Allow empty string only when neg_risk is False
            if not neg_risk and value == "":
                return value

            # Re-raise original error for other cases
            raise original_error

    @field_validator(
        "condition_id",
        "question_id",
        "neg_risk_market_id",
        "neg_risk_request_id",
        mode="wrap",
    )
    @classmethod
    def validate_condition_and_question_fields(
            cls, value: str, handler: ValidatorFunctionWrapHandler, info: ValidationInfo
    ) -> str:
        try:
            # First attempt standard validation
            return handler(value)
        except ValueError as original_error:
            active = info.data.get("active", False)
            # Allow empty string only when active is False
            if not active:
                return value
            # Re-raise original error for other cases
            raise original_error


class OpenOrder(BaseModel):
    order_id: Keccak256 = Field(alias="id")
    status: str
    owner: str
    maker_address: str
    condition_id: str = Field(alias="market")
    token_id: str = Field(alias="asset_id")
    side: Literal["BUY", "SELL"]
    original_size: float
    size_matched: float
    price: float
    outcome: str
    expiration: datetime
    order_type: Literal["GTC", "FOK", "GTD"]
    associate_trades: list[str]
    created_at: datetime

class Order(BaseModel):
    order_id: Keccak256
    owner: str
    maker_address: EthAddress
    matched_amount: float
    price: float
    fee_rate_bps: float
    token_id: str = Field(alias="asset_id")
    outcome: str

class PolygonTrade(BaseModel):
    trade_id: str = Field(alias="id")
    taker_order_id: Keccak256
    condition_id: Keccak256 = Field(alias="market")
    trade_id: str = Field(alias="id")
    side: Literal["BUY", "SELL"]
    size: float
    fee_rate_bps: float
    price: float
    status: str # change to literals MINED, CONFIRMED
    match_time: datetime
    last_update: datetime
    outcome: str
    bucket_index: int
    owner: str
    maker_address: EthAddress
    transaction_hash: Keccak256
    maker_orders: list[Order]
    trader_side: Literal["TAKER", "MAKER"]


class OrderArgs(BaseModel):
    token_id: str
    """
    TokenID of the Conditional token asset being traded
    """

    price: float
    """
    Price used to create the order
    """

    size: float
    """
    Size in terms of the ConditionalToken
    """

    side: str
    """
    Side of the order
    """

    fee_rate_bps: int = 0
    """
    Fee rate, in basis points, charged to the order maker, charged on proceeds
    """

    nonce: int = 0
    """
    Nonce used for onchain cancellations
    """

    expiration: int = 0
    """
    Timestamp after which the order is expired.
    """

    taker: str = ZERO_ADDRESS
    """
    Address of the order taker. The zero address is used to indicate a public order.
    """


class MarketOrderArgs(BaseModel):
    token_id: str
    """
    TokenID of the Conditional token asset being traded
    """

    amount: float
    """
    Amount in terms of Collateral.
    """

    price: float = 0.0
    """
    Price used to create the order.
    """

    fee_rate_bps: int = 0
    """
    Fee rate, in basis points, charged to the order maker, charged on proceeds.
    """

    nonce: int = 0
    """
    Nonce used for onchain cancellations.
    """

    taker: str = ZERO_ADDRESS
    """
    Address of the order taker. The zero address is used to indicate a public order.
    """


class TradeParams(BaseModel):
    id: Optional[str] = None
    maker_address: Optional[str] = None
    market: Optional[str] = None
    asset_id: Optional[str] = None
    before: Optional[int] = None
    after: Optional[int] = None


class OpenOrderParams(BaseModel):
    order_id: Optional[str] = None
    condition_id: Optional[str] = None
    token_id: Optional[str] = None


class DropNotificationParams(BaseModel):
    ids: Optional[list[str]] = None


class OrderSummary(BaseModel):
    price: Optional[float] = None
    size: Optional[float] = None


class OrderBookSummary(BaseModel):
    market: Optional[Keccak256] = None
    token_id: Optional[str] = Field(None, alias="asset_id")
    timestamp: Optional[datetime] = None
    hash: Optional[str] = None
    bids: Optional[list[OrderSummary]] = None
    asks: Optional[list[OrderSummary]] = None

    @field_serializer("bids", "asks")
    def serialize_sizes(self, orders: list[OrderSummary]) -> list[dict]:
        return [
            {
                "price": f"{order.price:.3f}".rstrip("0").rstrip("."),
                "size": f"{order.size:.2f}".rstrip("0").rstrip("."),
            }
            for order in orders
        ]

    @field_serializer("timestamp")
    def serialize_timestamp(self, ts: Optional[datetime]) -> Optional[str]:
        if ts is None:
            return None
        # Convert to millisecond timestamp string without decimal places
        return str(int(ts.timestamp() * 1000))


class AssetType(str, Enum):
    COLLATERAL = "COLLATERAL"
    CONDITIONAL = "CONDITIONAL"


class BalanceAllowanceParams(BaseModel):
    asset_type: Optional[AssetType] = None
    token_id: Optional[str] = None
    signature_type: int = -1


class OrderType(str, Enum):
    GTC = "GTC"  # Good Till Cancelled
    FOK = "FOK"  # Fill or Kill
    GTD = "GTD"  # Good Till Date


class OrderScoringParams(BaseModel):
    orderId: str


class OrdersScoringParams(BaseModel):
    orderIds: list[str]


TickSize = Literal["0.1", "0.01", "0.001", "0.0001"]


class CreateOrderOptions(BaseModel):
    tick_size: TickSize
    neg_risk: bool


class PartialCreateOrderOptions(BaseModel):
    tick_size: Optional[TickSize] = None
    neg_risk: Optional[bool] = None


class RoundConfig(BaseModel):
    price: float
    size: float
    amount: float


class ContractConfig(BaseModel):
    """
    Contract Configuration
    """

    exchange: EthAddress
    """
    The exchange contract responsible for matching orders.
    """

    collateral: EthAddress
    """
    The ERC20 token used as collateral for the exchange's markets.
    """

    conditional_tokens: EthAddress
    """
    The ERC1155 conditional tokens contract.
    """

class User(BaseModel):
    address: EthAddress = Field(alias="proxyWallet")
    name: str
    bio: str
    profile_image: str = Field(alias="profileImage")
    profile_image_optimized: str = Field(alias="profileImageOptimized")

class UserProfit(User):
    amount: float
    pseudonym: str

class UserRank(User):
    amount: float
    rank: int

class OrderPostResponse(BaseModel):
    error_msg: str = Field(alias="errorMsg")
    order_id: Keccak256 = Field(alias="orderID")
    taking_amount: str = Field(alias="takingAmount")
    making_amount: str = Field(alias="makingAmount")
    status: str = Literal["live"]
    transaction_hashes: Optional[list[str]] = Field(alias="transactionsHashes")
    success: bool

class OrderCancelResponse(BaseModel):
    not_canceled: Optional[dict[Keccak256, str]]
    canceled: Optional[list[Keccak256]]
