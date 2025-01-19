from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

from .common import EthAddress, Keccak256


class Position(BaseModel):
    proxyWallet: EthAddress
    asset: str
    conditionId: Keccak256
    size: float
    avgPrice: float
    initialValue: float
    currentValue: float
    cashPnl: float
    percentPnl: float
    totalBought: float
    realizedPnl: float
    percentRealizedPnl: float
    curPrice: float
    redeemable: bool
    title: str
    slug: str
    icon: str
    eventSlug: str
    outcome: str
    outcomeIndex: int
    oppositeOutcome: str
    oppositeAsset: str
    endDate: datetime
    negativeRisk: bool


class Trade(BaseModel):
    proxyWallet: EthAddress
    side: Literal["BUY", "SELL"]
    asset: str
    conditionId: Keccak256
    size: float
    price: float
    timestamp: datetime
    title: str
    slug: str
    icon: str
    eventSlug: str
    outcome: str
    outcomeIndex: int
    name: str
    pseudonym: str
    bio: str
    profileImage: str
    profileImageOptimized: str
    transactionHash: Keccak256


class Activity(BaseModel):
    proxyWallet: EthAddress
    timestamp: datetime
    conditionId: Keccak256
    type: Literal["TRADE", "SPLIT", "MERGE", "REDEEM", "REWARD", "CONVERSION"]
    size: float
    usdcSize: float
    transactionHash: Keccak256
    price: float
    asset: str
    side: Optional[str]
    outcomeIndex: int
    title: str
    slug: str
    icon: str
    eventSlug: str
    outcome: str
    name: str
    pseudonym: str
    bio: str
    profileImage: str
    profileImageOptimized: str


class Holder(BaseModel):
    proxyWallet: EthAddress
    bio: str
    asset: str
    pseudonym: str
    amount: float
    displayUsernamePublic: bool
    outcomeIndex: int
    name: str
    profileImage: str
    profileImageOptimized: str


class HolderResponse(BaseModel):
    token: str
    holders: List[Holder]


class ValueResponse(BaseModel):
    user: EthAddress
    value: float
