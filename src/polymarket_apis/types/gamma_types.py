from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import (
    BaseModel,
    Field,
    Json,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    field_validator,
)

from .common import EthAddress, Keccak256, TimestampWithTZ


class Event(BaseModel):
    # Identifiers
    id: str
    slug: str
    ticker: Optional[str] = None

    # Core event information
    title: str
    description: Optional[str] = None
    resolution_source: Optional[str] = Field(None, alias="resolutionSource")
    category: Optional[str] = None

    # Media URLs
    image: Optional[str] = None
    icon: Optional[str] = None

    # Datetime
    start_date: Optional[datetime] = Field(None, alias="startDate")
    end_date: Optional[datetime] = Field(None, alias="endDate")
    creation_date: Optional[datetime] = Field(None, alias="creationDate")
    created_at: Optional[datetime] = Field(alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")
    published_at: Optional[datetime] = Field(None, alias="publishedAt")
    closed_time: Optional[datetime] = Field(None, alias="closedTime")

    # Status flags
    active: bool
    closed: bool
    archived: Optional[bool] = None
    new: Optional[bool] = None
    featured: Optional[bool] = None
    restricted: Optional[bool] = None
    cyom: bool
    automatically_active: Optional[bool] = Field(None, alias="automaticallyActive")

    # Financial metrics
    liquidity: Optional[float] = None
    volume: Optional[float] = None
    open_interest: Optional[int] = Field(None, alias="openInterest")
    competitive: Optional[float] = None
    volume_24hr: Optional[float] = Field(None, alias="volume24hr")
    liquidity_amm: Optional[float] = Field(None, alias="liquidityAmm")
    liquidity_clob: Optional[float] = Field(None, alias="liquidityClob")

    # Related data
    markets: Optional[list[GammaMarket]] = None
    series: Optional[list[Series]] = None
    tags: Optional[list[Tag]] = None

    # User interaction
    comment_count: Optional[int] = Field(None, alias="commentCount")

    # Display and functionality settings
    sort_by: Optional[str] = Field(None, alias="sortBy")
    show_all_outcomes: bool = Field(alias="showAllOutcomes")
    show_market_images: bool = Field(alias="showMarketImages")
    gmp_chart_mode: Optional[str] = Field(None, alias="gmpChartMode")

    # Negative risk settings
    enable_neg_risk: bool = Field(alias="enableNegRisk")
    neg_risk: Optional[bool] = Field(None, alias="negRisk")
    neg_risk_market_id: Optional[str] = Field(None, alias="negRiskMarketID")
    neg_risk_augmented: Optional[bool] = Field(None, alias="negRiskAugmented")

    # Order book settings
    enable_order_book: Optional[bool] = Field(None, alias="enableOrderBook")


class GammaMarket(BaseModel):
    # Identifiers
    id: str
    slug: str
    condition_id: Keccak256 = Field(alias="conditionId")
    question_id: Optional[Keccak256] = Field(None, alias="questionID")

    # Core market information
    question: str
    description: str
    resolution_source: Optional[str] = Field(None, alias="resolutionSource")
    outcome: Optional[list] = None
    outcome_prices: Optional[Json[list[float]] | list[float]] = Field(None, alias="outcomePrices")

    # Media URLs
    image: Optional[str] = None
    icon: Optional[str] = None

    # Datetime
    start_date: Optional[datetime] = Field(None, alias="startDate")
    end_date: Optional[datetime] = Field(None, alias="endDate")
    created_at: datetime = Field(alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")
    start_date_iso: Optional[datetime] = Field(None, alias="startDateIso")
    end_date_iso: Optional[datetime] = Field(None, alias="endDateIso")
    deployed_timestamp: Optional[datetime] = Field(None, alias="deployedTimestamp")
    accepting_orders_timestamp: Optional[datetime] = Field(None, alias="acceptingOrdersTimestamp")

    # Status flags
    active: bool
    closed: bool
    archived: bool
    new: Optional[bool] = None
    featured: Optional[bool] = None
    restricted: bool
    ready: bool
    deployed: Optional[bool] = None
    funded: bool
    cyom: bool
    approved: bool

    # Financial metrics
    liquidity: Optional[float] = None
    volume: Optional[float] = None
    volume_num: Optional[float] = Field(None, alias="volumeNum")
    liquidity_num: Optional[float] = Field(None, alias="liquidityNum")
    volume_24hr: Optional[float] = Field(None, alias="volume24hr")
    volume_24hr_clob: Optional[float] = Field(None, alias="volume24hrClob")
    volume_clob: Optional[float] = Field(None, alias="volumeClob")
    liquidity_clob: Optional[float] = Field(None, alias="liquidityClob")
    competitive: Optional[float] = None
    spread: float

    # Order book settings
    enable_order_book: Optional[bool] = Field(None, alias="enableOrderBook")
    order_price_min_tick_size: Optional[float] = Field(
        None, alias="orderPriceMinTickSize",
    )
    order_min_size: Optional[float] = Field(None, alias="orderMinSize")
    accepting_orders: Optional[bool] = Field(None, alias="acceptingOrders")

    # Related data
    events: Optional[list[Event]] = None
    clob_rewards: Optional[list[ClobReward]] = Field(None, alias="clobRewards")

    # User interaction
    comment_count: Optional[int] = Field(None, alias="commentCount")

    # Market maker information
    market_maker_address: str = Field(alias="marketMakerAddress")

    # Additional settings
    group_item_title: Optional[str] = Field(None, alias="groupItemTitle")
    group_item_threshold: Optional[int] = Field(None, alias="groupItemThreshold")
    token_ids: Optional[Json[list[str]] | list[str]] = Field(None, alias="clobTokenIds")
    uma_bond: Optional[int] = Field(None, alias="umaBond")
    uma_reward: Optional[float] = Field(None, alias="umaReward")
    neg_risk: Optional[bool] = Field(None, alias="negRisk")
    pager_duty_notification_enabled: bool = Field(alias="pagerDutyNotificationEnabled")
    review_status: Optional[str] = Field(None, alias="reviewStatus")
    rewards_min_size: int = Field(alias="rewardsMinSize")
    rewards_max_spread: float = Field(alias="rewardsMaxSpread")

    # Resolution information
    submitted_by: Optional[str] = None
    resolved_by: Optional[EthAddress] = Field(None, alias="resolvedBy")
    has_reviewed_dates: Optional[bool] = Field(None, alias="hasReviewedDates")

    @field_validator("condition_id", mode="wrap")
    @classmethod
    def validate_condition_id(
            cls, value: str, handler: ValidatorFunctionWrapHandler, info: ValidationInfo,
    ) -> str:
        try:
            # First attempt standard Keccak256 validation
            return handler(value)
        except ValueError:
            active = info.data.get("active", False)

            # Only allow empty string when inactive
            if not active and value == "":
                return value

            # Re-raise original error for other cases
            raise

class ClobReward(BaseModel):
    # Identifiers
    id: str
    condition_id: Keccak256 = Field(alias="conditionId")

    # Reward information
    asset_address: str = Field(alias="assetAddress")
    rewards_amount: float = Field(alias="rewardsAmount")
    rewards_daily_rate: Optional[float] = Field(None, alias="rewardsDailyRate")

    # Datetime
    start_date: datetime = Field(alias="startDate")
    end_date: datetime = Field(alias="endDate")


class Tag(BaseModel):
    # Identifiers
    id: str
    label: str
    slug: str

    # Display settings
    force_show: Optional[bool] = Field(None, alias="forceShow")
    force_hide: Optional[bool] = Field(None, alias="forceHide")

    # Datetime
    published_at: Optional[TimestampWithTZ | datetime] = Field(None, alias="publishedAt")
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")

    # User information
    created_by: Optional[int] = Field(None, alias="createdBy")
    updated_by: Optional[int] = Field(None, alias="updatedBy")


class Series(BaseModel):
    # Identifiers
    id: str
    slug: str
    ticker: str
    title: str

    # Series characteristics
    series_type: Optional[str] = Field(None,  alias="seriesType")
    recurrence: Optional[str] = None
    layout: Optional[str] = None

    # Media URLs
    icon: Optional[str] = None
    image: Optional[str] = None

    # Datetime
    start_date: Optional[datetime] = Field(None, alias="startDate")
    created_at: datetime = Field(alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")
    published_at: Optional[TimestampWithTZ | datetime] = Field(None, alias="publishedAt")

    # Status flags
    active: Optional[bool] = None
    archived: Optional[bool] = None
    closed: Optional[bool] = None
    featured: Optional[bool] = None
    new: Optional[bool] = None
    restricted: Optional[bool] = None

    # Financial metrics
    liquidity: Optional[float] = None
    volume: Optional[float] = None
    volume_24hr: Optional[float] = Field(None, alias="volume24hr")
    competitive: Optional[str] = None

    # User interaction
    comment_count: int = Field(alias="commentCount")
    comments_enabled: Optional[bool] = Field(None, alias="commentsEnabled")

    # User information
    created_by: Optional[str] = Field(None, alias="createdBy")
    updated_by: Optional[str] = Field(None, alias="updatedBy")

class QueryEvent(BaseModel):
    # Identifiers and description
    id: str
    ticker: Optional[str] = None
    slug: str
    title: str
    description: Optional[str] = None

    # Datetime
    start_date: Optional[datetime] = Field(None, alias="startDate")
    creation_date: Optional[datetime] = Field(None, alias="creationDate")
    end_date: Optional[datetime] = Field(None, alias="endDate")
    created_at: datetime = Field(alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")

    # Resolution info
    resolution_source: Optional[str] = Field(None, alias="resolutionSource")

    # Media URLs
    image: Optional[str] = None
    icon: Optional[str] = None

    # Status flags
    active: bool
    closed: bool
    archived: Optional[bool] = None
    new: Optional[bool] = None
    featured: Optional[bool] = None
    restricted: Optional[bool] = None
    automatically_active: Optional[bool] = Field(None, alias="automaticallyActive")
    pending_deployment: Optional[bool] = Field(None, alias="pendingDeployment")
    deploying: Optional[bool] = None

    # Financial metrics
    liquidity: Optional[float] = None
    liquidity_clob: Optional[float] = Field(None, alias="liquidityClob")
    volume: Optional[float] = None
    open_interest: Optional[int] = Field(None, alias="openInterest")
    competitive: Optional[float] = None
    volume_24hr: Optional[float] = Field(None, alias="volume24hr")
    volume_1wk: Optional[float] = Field(None, alias="volume1wk")
    volume_1mo: Optional[float] = Field(None, alias="volume1mo")
    volume_1yr: Optional[float] = Field(None, alias="volume1yr")

    # User interaction metrics
    comment_count: Optional[int] = Field(None, alias="commentCount")

    # Related entities
    markets: Optional[list[GammaMarket]] = None
    tags: Optional[list[Tag]] = None

    # Feature toggles
    enable_order_book: Optional[bool] = Field(None, alias="enableOrderBook")
    enable_neg_risk: bool = Field(alias="enableNegRisk")
    neg_risk_augmented: Optional[bool] = Field(None, alias="negRiskAugmented")
    cyom: bool
    show_all_outcomes: bool = Field(alias="showAllOutcomes")
    show_market_images: bool = Field(alias="showMarketImages")

class Pagination(BaseModel):
    has_more: bool = Field(alias="hasMore")
    total_results: int = Field(alias="totalResults")

class EventList(BaseModel):
    events: Optional[list[QueryEvent]] = None
    pagination: Pagination

class QueryMarket(BaseModel):
    # Identifiers
    slug: str
    question: str
    group_item_title: Optional[str] = Field(None, alias="groupItemTitle")

    # Market data
    outcomes: Optional[list] = None
    outcome_prices: Optional[Json[list[float]] | list[float]] = Field(None, alias="outcomePrices")
    last_trade_price: Optional[float] = Field(None, alias="lastTradePrice")
    best_ask: Optional[float] = Field(None, alias="bestAsk")
    best_bid: Optional[float] = Field(None, alias="bestBid")
    spread: float

    # Status flags
    closed: bool
    archived: bool
