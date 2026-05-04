import logging
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any, Literal, Optional, TypeVar, Union, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    ValidationError,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    field_serializer,
    field_validator,
)

from ..types.common import EthAddress, Keccak256, TimeseriesPoint
from ..utilities.constants import BYTES32_ZERO
from ..utilities.order_builder.model import SignedOrder

logger = logging.getLogger(__name__)


class ApiCreds(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str = Field(alias="apiKey")
    secret: str
    passphrase: str


class RequestArgs(BaseModel):
    method: Literal["GET", "POST", "DELETE"]
    request_path: str
    body: Any = None


class TokenValue(BaseModel):
    token_id: str
    value: float


class Midpoint(TokenValue):
    pass


class Spread(TokenValue):
    pass


TokenValueDict = RootModel[dict[str, float]]


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


TokenBidAskDict = RootModel[dict[str, BidAsk]]


class Token(BaseModel):
    token_id: str
    outcome: str
    price: float
    winner: Optional[bool] = None


class PriceHistory(BaseModel):
    token_id: str
    history: list[TimeseriesPoint]


T = TypeVar("T")


class PaginatedResponse[T](BaseModel):
    data: list[T]
    next_cursor: str
    limit: int
    count: int


class RewardRate(BaseModel):
    asset_address: EthAddress
    rewards_daily_rate: float


class RewardConfig(BaseModel):
    asset_address: str
    rewards_daily_rate: float = Field(alias="rate_per_day")

    start_date: datetime
    end_date: datetime

    reward_id: Optional[str] = Field(None, alias="id")
    total_rewards: float
    total_days: Optional[int] = None

    @field_validator("reward_id", mode="before")
    def convert_id_to_str(cls, v: int | Optional[str]) -> Optional[str]:
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


class RewardMarket(BaseModel):
    market_id: str
    condition_id: Keccak256
    question: str
    market_slug: str
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


class MarketRewards(BaseModel):
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


class MarketIDs(BaseModel):
    condition_id: Keccak256
    primary_token_id: str
    secondary_token_id: str


class ClobMarket(BaseModel):
    # Core market information
    token_ids: list[Token] = Field(alias="tokens")
    condition_id: Keccak256
    question_id: Keccak256
    question: str
    description: str
    market_slug: str
    end_date_iso: Optional[datetime]
    game_start_time: Optional[datetime] = None
    seconds_delay: int

    # Order book settings
    enable_order_book: bool
    accepting_orders: bool
    accepting_order_timestamp: Optional[datetime]
    minimum_order_size: float
    minimum_tick_size: float

    # Status flags
    active: bool
    closed: bool
    archived: bool

    # Negative risk settings
    neg_risk: bool
    neg_risk_market_id: Keccak256
    neg_risk_request_id: Keccak256

    # Fee structure
    fpmm: str
    maker_base_fee: Optional[Literal[0, 1000]] = None
    taker_base_fee: Optional[Literal[0, 1000]] = None

    # Features
    notifications_enabled: bool
    is_50_50_outcome: bool

    # Visual representation
    icon: str
    image: str

    # Rewards configuration
    rewards: Optional[Rewards]

    # Tags
    tags: Optional[list[str]]

    @field_validator("neg_risk_market_id", "neg_risk_request_id", mode="wrap")
    @classmethod
    def validate_neg_risk_fields(
        cls, value: str, handler: ValidatorFunctionWrapHandler, info: ValidationInfo
    ) -> str | None:
        try:
            return cast("str | None", handler(value))
        except ValidationError as e:
            neg_risk = info.data.get("neg_risk", False)
            active = info.data.get("active", False)
            if not neg_risk and value == "":
                return value
            if not active:
                return value
            if neg_risk and value == "":
                for _ in e.errors():
                    msg = (
                        "Poorly setup market: negative risk is True, but either neg_risk_market_id or neg_risk_request_id is missing. "
                        f" Question: {info.data.get('question')}; Market slug: {info.data.get('market_slug')} \n"
                    )
                    logger.warning(msg)
            return None

    @field_validator("condition_id", "question_id", mode="wrap")
    @classmethod
    def validate_condition_fields(
        cls, value: str, handler: ValidatorFunctionWrapHandler, info: ValidationInfo
    ) -> str:
        try:
            return cast("str", handler(value))
        except ValueError:
            active = info.data.get("active", False)
            if not active:
                return value
            raise


class ClobFeeData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rate: float = Field(alias="r")
    exponent: int = Field(alias="e")
    taker_only: bool = Field(alias="to")


class FeeInfo(BaseModel):
    rate: float = 0.0
    exponent: float = 0.0


class ClobMarketInfoToken(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    token_id: str = Field(alias="t")
    outcome: str = Field(alias="o")


class ClobMarketInfoRewards(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    min_size: Optional[float] = Field(default=None, alias="mi", ge=0)
    max_spread: Optional[float] = Field(default=None, alias="ma", ge=0)
    enabled: Optional[bool] = Field(default=None, alias="e")
    minimum_order_age_seconds: Optional[int] = Field(default=None, alias="moas", ge=0)


class ClobMarketInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    game_start_time: Optional[datetime] = Field(None, alias="gst")
    rewards: ClobMarketInfoRewards = Field(alias="r")
    tokens: list[ClobMarketInfoToken] = Field(alias="t")
    minimum_order_size: float = Field(alias="mos")
    minimum_tick_size: float = Field(alias="mts")
    maker_base_fee: Optional[int] = Field(None, alias="mbf")
    taker_base_fee: Optional[int] = Field(None, alias="tbf")
    rfq_enabled: Optional[bool] = Field(None, alias="rfqe")
    taker_order_delay_enabled: Optional[bool] = Field(None, alias="itode")
    blockaid_check_enabled: bool = Field(alias="ibce")
    fee_data: Optional[ClobFeeData] = Field(None, alias="fd")
    minimum_order_age_seconds: Optional[int] = Field(None, alias="oas")


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
    order_type: Literal["GTC", "GTD"]
    associate_trades: list[str]
    created_at: datetime


class MakerOrder(BaseModel):
    token_id: str = Field(alias="asset_id")
    order_id: Keccak256
    maker_address: EthAddress
    owner: str
    matched_amount: float
    price: float
    outcome: str


class PolygonTrade(BaseModel):  # type: ignore[no-redef] # id is the same as trade_id
    trade_id: str = Field(alias="id")
    taker_order_id: Keccak256
    condition_id: Keccak256 = Field(alias="market")
    id: str
    side: Literal["BUY", "SELL"]
    size: float
    fee_rate_bps: float
    price: float
    status: str  # change to literals MINED, CONFIRMED
    match_time: datetime
    last_update: datetime
    outcome: str
    bucket_index: int
    owner: str
    maker_address: EthAddress
    transaction_hash: Keccak256
    maker_orders: list[MakerOrder]
    trader_side: Literal["TAKER", "MAKER"]


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
    price: float
    size: float


class PriceLevel(OrderSummary):
    side: Literal["BUY", "SELL"]


TickSize = Literal["0.1", "0.01", "0.001", "0.0001"]


class OrderBookSummary(BaseModel):
    condition_id: Keccak256 = Field(alias="market")
    token_id: str = Field(alias="asset_id")
    timestamp: datetime
    hash: str
    bids: list[OrderSummary]
    asks: list[OrderSummary]
    tick_size: Optional[TickSize] = None
    last_trade_price: Optional[float] = None
    min_order_size: Optional[float] = None
    neg_risk: Optional[bool] = None

    @field_validator("last_trade_price", mode="before")
    def handle_empty_last_trade_price(
        cls, v: Optional[float] | Literal[""]
    ) -> Optional[float]:
        if v == "":
            return None
        return v

    @field_serializer("bids", "asks")
    def serialize_sizes(self, orders: list[OrderSummary]) -> list[dict[str, str]]:
        return [
            {
                "price": f"{order.price:.3f}".rstrip("0").rstrip("."),
                "size": f"{order.size:.2f}".rstrip("0").rstrip("."),
            }
            for order in orders
        ]

    @field_serializer("timestamp")
    def serialize_timestamp(self, ts: datetime) -> str:
        # Convert to millisecond timestamp string without decimal places
        return str(int(ts.timestamp() * 1000))


class AssetType(StrEnum):
    COLLATERAL = "COLLATERAL"
    CONDITIONAL = "CONDITIONAL"


class BalanceAllowanceParams(BaseModel):
    asset_type: Optional[AssetType] = None
    token_id: Optional[str] = None
    signature_type: int = -1


class OrderType(StrEnum):
    GTC = "GTC"  # Good Till Cancelled
    GTD = "GTD"  # Good Till Date
    FOK = "FOK"  # Fill or Kill
    FAK = "FAK"  # Fill and Kill


class SignatureType(IntEnum):
    EOA = 0
    POLY_PROXY = 1
    POLY_GNOSIS_SAFE = 2
    POLY_1271 = 3


class CreateOrderOptions(BaseModel):
    tick_size: TickSize
    neg_risk: bool


class PartialCreateOrderOptions(BaseModel):
    tick_size: Optional[TickSize] = None
    neg_risk: Optional[bool] = None


class RoundConfig(BaseModel):
    price: int
    size: int
    amount: int


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

    expiration: int = 0
    """
    Timestamp after which the order is expired. This is posted to the API, but is
    not part of the CLOB V2 signed EIP-712 order.
    """

    builder_code: str = BYTES32_ZERO
    """
    Optional CLOB V2 builder attribution code.
    """

    metadata: str = BYTES32_ZERO
    """
    Optional CLOB V2 order metadata.
    """


class MarketOrderArgs(BaseModel):
    token_id: str
    """
    TokenID of the Conditional token asset being traded
    """

    amount: float
    """
    BUY orders: $$$ Amount to buy
    SELL orders: Shares to sell
    """

    side: str
    """
    Side of the order
    """

    price: float = 0
    """
    Price used to create the order
    """

    order_type: OrderType = OrderType.FOK

    user_usdc_balance: float = 0
    """
    User pUSD balance available for market order sizing. Reserved for V2 parity.
    """

    builder_code: str = BYTES32_ZERO
    """
    Optional CLOB V2 builder attribution code.
    """

    metadata: str = BYTES32_ZERO
    """
    Optional CLOB V2 order metadata.
    """


class PostOrdersArgs(BaseModel):
    order: SignedOrder
    order_type: OrderType = OrderType.GTC

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ContractConfig(BaseModel):
    """Contract Configuration."""

    exchange: EthAddress
    """
    The V2 exchange contract responsible for matching orders.
    """

    neg_risk_exchange: EthAddress
    """
    The V2 negative-risk exchange contract responsible for matching orders.
    """

    neg_risk_adapter: EthAddress
    """
    The negative-risk adapter contract.
    """

    collateral: EthAddress
    """
    The ERC20 token used as pUSD collateral for the exchange's markets.
    """

    conditional_tokens: EthAddress
    """
    The ERC1155 conditional tokens contract.
    """


class OrderPostResponse(BaseModel):
    error_msg: str = Field(alias="errorMsg")
    order_id: Union[Keccak256, Literal[""]] = Field(alias="orderID")
    taking_amount: str = Field(alias="takingAmount")
    making_amount: str = Field(alias="makingAmount")
    status: Literal["live", "matched", "delayed", "unmatched", ""]
    success: bool


class OrderCancelResponse(BaseModel):
    not_canceled: Optional[dict[Keccak256, str]]
    canceled: Optional[list[Keccak256]]


CryptoOutcome = Literal["up", "down"]


class PastResultsData(BaseModel):
    outcomes_by_slug: dict[str, CryptoOutcome] = Field(alias="outcomesBySlug")


class PastResultsResponse(BaseModel):
    data: PastResultsData
