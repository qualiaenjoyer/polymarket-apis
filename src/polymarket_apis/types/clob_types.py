from enum import Enum
from typing import Any, List, Literal, Optional

from pydantic import BaseModel

from ..utilities.constants import ZERO_ADDRESS

# TODO check types


class ApiCreds(BaseModel):
    apiKey: str
    secret: str
    passphrase: str


class RequestArgs(BaseModel):
    method: Literal["GET", "POST", "DELETE"]
    request_path: str
    body: Optional[Any] = None


class BookParams(BaseModel):
    token_id: str
    side: Literal["BUY", "SELL"]


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
    id: Optional[str] = None
    market: Optional[str] = None
    asset_id: Optional[str] = None


class DropNotificationParams(BaseModel):
    ids: Optional[List[str]] = None


class OrderSummary(BaseModel):
    price: Optional[str] = None
    size: Optional[str] = None

    @property
    def __dict__(self):
        return self.model_dump()

    @property
    def json(self):
        return self.json()


class OrderSummary(BaseModel):
    price: Optional[str] = None
    size: Optional[str] = None

    @property
    def dict(self):
        return self.model_dump()

    @property
    def json(self):
        return self.json()


class OrderBookSummary(BaseModel):
    market: Optional[str] = None
    asset_id: Optional[str] = None
    timestamp: Optional[str] = None
    bids: Optional[List[OrderSummary]] = None
    asks: Optional[List[OrderSummary]] = None
    hash: Optional[str] = None

    @property
    def dict(self):
        return self.model_dump()

    @property
    def json(self):
        return self.json(separators=(",", ":"))


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
    orderIds: List[str]


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

    exchange: str
    """
    The exchange contract responsible for matching orders.
    """

    collateral: str
    """
    The ERC20 token used as collateral for the exchange's markets.
    """

    conditional_tokens: str
    """
    The ERC1155 conditional tokens contract.
    """
