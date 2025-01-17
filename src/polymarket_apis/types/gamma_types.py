from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Json
from datetime import datetime
from polymarket_apis.types.common import EthAddress, Keccak256, TimestampWithTZ


class Event(BaseModel):
    id: str  # "11421"
    ticker: Optional[str] = None
    slug: str
    title: str
    description: Optional[str] = None
    resolutionSource: Optional[str] = None
    startDate: Optional[datetime] = None
    creationDate: Optional[datetime] = (
        None  # fine in market event but missing from events response
    )
    endDate: Optional[datetime] = None
    image: str
    icon: str
    active: bool
    closed: bool
    archived: Optional[bool] = None
    new: Optional[bool] = None
    featured: Optional[bool] = None
    restricted: Optional[bool] = None
    liquidity: Optional[float] = None
    volume: Optional[float] = None
    openInterest: Optional[int] = None
    sortBy: Optional[str] = None
    category: Optional[str] = None
    published_at: Optional[TimestampWithTZ] = None
    createdAt: datetime  # 2024-07-08T01:06:23.982796Z,
    updatedAt: Optional[datetime] = None  # 2024-07-15T17:12:48.601056Z,
    competitive: Optional[float] = None
    volume24hr: Optional[float] = None
    liquidityAmm: Optional[float] = None
    liquidityClob: Optional[float] = None
    commentCount: Optional[int] = None
    markets: Optional[list[Market]] = None
    # markets: list[str, 'Market'] # forward reference Market defined below - TODO: double check this works as intended
    series: Optional[list[Series]] = None
    tags: Optional[list[Tag]] = None
    cyom: bool
    closedTime: Optional[datetime] = None
    showAllOutcomes: bool
    showMarketImages: bool
    enableNegRisk: bool
    enableOrderBook: Optional[bool] = None
    negRisk: Optional[bool] = None
    negRiskMarketID: Optional[str] = None
    automaticallyActive: Optional[bool] = None
    negRiskAugmented: Optional[bool] = None
    gmpChartMode: Optional[str] = None


class Market(BaseModel):
    id: int
    question: str
    conditionId: Keccak256
    slug: str
    resolutionSource: Optional[str] = None
    endDate: Optional[datetime] = None
    liquidity: Optional[float] = None
    startDate: Optional[datetime] = None
    image: Optional[str] = None
    icon: Optional[str] = None
    description: str
    outcome: Optional[list] = None
    outcomePrices: Optional[Json[list]] = None
    volume: Optional[float] = None
    active: bool
    closed: bool
    marketMakerAddress: str
    createdAt: datetime  # date type worth enforcing for dates?
    updatedAt: Optional[datetime] = None
    new: Optional[bool] = None
    featured: Optional[bool] = None
    submitted_by: Optional[EthAddress] = None
    archived: bool
    resolvedBy: Optional[EthAddress] = None
    restricted: bool
    groupItemTitle: Optional[str] = None
    groupItemThreshold: Optional[int] = None
    questionID: Optional[Keccak256] = None
    enableOrderBook: Optional[bool] = None
    orderPriceMinTickSize: Optional[float] = None
    orderMinSize: Optional[float] = None
    volumeNum: Optional[float] = None
    liquidityNum: Optional[float] = None
    endDateIso: Optional[datetime] = None  # iso format date
    startDateIso: Optional[datetime] = None
    hasReviewedDates: Optional[bool] = None
    volume24hr: Optional[float] = None
    clobTokenIds: Optional[Json[list[str]]] = None
    umaBond: Optional[int] = None  # returned as string from api?
    umaReward: Optional[float] = None  # returned as string from api?
    volume24hrClob: Optional[float] = None
    volumeClob: Optional[float] = None
    liquidityClob: Optional[float] = None
    acceptingOrders: Optional[bool] = None
    negRisk: Optional[bool] = None
    commentCount: Optional[int] = None
    _sync: bool
    events: Optional[list[Event]] = None
    ready: bool
    deployed: Optional[bool] = None
    funded: bool
    deployedTimestamp: Optional[datetime] = None  # utc z datetime string
    acceptingOrdersTimestamp: Optional[datetime] = None  # utc z datetime string,
    cyom: bool
    competitive: Optional[float] = None
    pagerDutyNotificationEnabled: bool
    reviewStatus: Optional[str] = None  # deployed, draft, etc.
    approved: bool
    clobRewards: Optional[list[ClobReward]] = None
    rewardsMinSize: int  # would make sense to allow float but we'll see
    rewardsMaxSpread: float
    spread: float


class ClobReward(BaseModel):
    id: str  # returned as string in api but really an int?
    conditionId: Keccak256
    assetAddress: str
    rewardsAmount: float  # only seen 0 but could be float?
    rewardsDailyRate: Optional[float] = None  # only seen ints but could be float?
    startDate: datetime  # yyyy-mm-dd formatted date string
    endDate: datetime  # yyyy-mm-dd formatted date string


class Tag(BaseModel):
    id: str
    label: str
    slug: str
    forceShow: Optional[bool] = None
    publishedAt: Optional[TimestampWithTZ] = None
    createdBy: Optional[int] = None
    createdAt: Optional[datetime] = None
    updatedBy: Optional[int] = None
    updatedAt: Optional[datetime] = None
    forceHide: Optional[bool] = None


class Series(BaseModel):
    active: bool
    archived: bool
    closed: bool
    commentCount: int
    commentsEnabled: Optional[bool] = None
    competitive: Optional[str] = None
    createdAt: datetime
    createdBy: Optional[str] = None
    featured: bool
    icon: Optional[str] = None
    id: str
    image: Optional[str] = None
    layout: Optional[str] = None
    liquidity: Optional[float] = None
    new: Optional[bool] = None
    publishedAt: Optional[TimestampWithTZ] = None
    recurrence: str
    restricted: bool
    seriesType: str
    slug: str
    startDate: Optional[datetime] = None
    ticker: str
    title: str
    updatedAt: datetime
    updatedBy: Optional[str] = None
    volume: Optional[float] = None
    volume24hr: Optional[float] = None
