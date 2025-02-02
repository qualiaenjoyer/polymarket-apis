from datetime import datetime
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field

from .common import EthAddress, Keccak256, EmptyString


class Position(BaseModel):
    # User identification
    proxyWallet: EthAddress

    # Asset information
    token_id: str = Field(alias="asset")
    condition_id: Keccak256 = Field(alias="conditionId")
    outcome: str
    outcomeIndex: int
    oppositeOutcome: str
    oppositeAsset: str

    # Position details
    size: float
    avgPrice: float
    curPrice: float
    redeemable: bool

    # Financial metrics
    initialValue: float
    currentValue: float
    cashPnl: float
    percentPnl: float
    totalBought: float
    realizedPnl: float
    percentRealizedPnl: float

    # Event information
    title: str
    slug: str
    icon: str
    eventSlug: str
    endDate: datetime
    negativeRisk: bool


class Trade(BaseModel):
    # User identification
    proxyWallet: EthAddress

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
    eventSlug: str
    outcome: str
    outcomeIndex: int

    # User profile
    name: str
    pseudonym: str
    bio: str
    profileImage: str
    profileImageOptimized: str

    # Transaction information
    transactionHash: Keccak256


class Activity(BaseModel):
    # User identification
    proxyWallet: EthAddress

    # Activity details
    timestamp: datetime
    condition_id: Union[Keccak256, EmptyString] = Field(alias="conditionId")
    type: Literal["TRADE", "SPLIT", "MERGE", "REDEEM", "REWARD", "CONVERSION"]
    size: float
    usdcSize: float
    price: float
    asset: str
    side: Optional[str]
    outcomeIndex: int

    # Event information
    title: str
    slug: str
    icon: str
    eventSlug: str
    outcome: str

    # User profile
    name: str
    pseudonym: str
    bio: str
    profileImage: str
    profileImageOptimized: str

    # Transaction information
    transactionHash: Keccak256


class Holder(BaseModel):
    # User identification
    proxyWallet: EthAddress

    # Holder details
    token_id: str = Field(alias="asset")
    amount: float
    outcomeIndex: int

    # User profile
    name: str
    pseudonym: str
    bio: str
    profileImage: str
    profileImageOptimized: str
    displayUsernamePublic: bool


class HolderResponse(BaseModel):
    # Asset information
    token_id: str = Field(alias="token")

    # Holders list
    holders: List[Holder]


class ValueResponse(BaseModel):
    # User identification
    user: EthAddress

    # Value information
    value: float
