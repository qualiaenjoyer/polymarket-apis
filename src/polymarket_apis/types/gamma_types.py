from __future__ import annotations

from datetime import datetime

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
    # Basic identification
    id: str
    slug: str
    ticker: str | None = None

    # Core event information
    title: str
    description: str | None = None
    resolution_source: str | None = Field(None, alias="resolutionSource")
    category: str | None = None

    # Visual representation
    image: str | None = None
    icon: str | None = None

    # Temporal information
    start_date: datetime | None = Field(None, alias="startDate")
    end_date: datetime | None = Field(None, alias="endDate")
    creation_date: datetime | None = Field(None, alias="creationDate")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime | None = Field(None, alias="updatedAt")
    published_at: TimestampWithTZ | None = None
    closed_time: datetime | None = Field(None, alias="closedTime")

    # Status flags
    active: bool
    closed: bool
    archived: bool | None = None
    new: bool | None = None
    featured: bool | None = None
    restricted: bool | None = None
    cyom: bool
    automatically_active: bool | None = Field(None, alias="automaticallyActive")

    # Financial metrics
    liquidity: float | None = None
    volume: float | None = None
    open_interest: int | None = Field(None, alias="openInterest")
    competitive: float | None = None
    volume_24hr: float | None = Field(None, alias="volume24hr")
    liquidity_amm: float | None = Field(None, alias="liquidityAmm")
    liquidity_clob: float | None = Field(None, alias="liquidityClob")

    # Related data
    markets: list[GammaMarket] | None = None
    series: list[Series] | None = None
    tags: list[Tag] | None = None

    # User interaction
    comment_count: int | None = Field(None, alias="commentCount")

    # Display and functionality settings
    sort_by: str | None = Field(None, alias="sortBy")
    show_all_outcomes: bool = Field(alias="showAllOutcomes")
    show_market_images: bool = Field(alias="showMarketImages")
    gmp_chart_mode: str | None = Field(None, alias="gmpChartMode")

    # Negative risk settings
    enable_neg_risk: bool = Field(alias="enableNegRisk")
    neg_risk: bool | None = Field(None, alias="negRisk")
    neg_risk_market_id: str | None = Field(None, alias="negRiskMarketID")
    neg_risk_augmented: bool | None = Field(None, alias="negRiskAugmented")

    # Order book settings
    enable_order_book: bool | None = Field(None, alias="enableOrderBook")


class GammaMarket(BaseModel):
    # Basic identification
    id: str
    slug: str
    condition_id: Keccak256 = Field(alias="conditionId")
    question_id: Keccak256 | None = Field(None, alias="questionID")

    # Core market information
    question: str
    description: str
    resolution_source: str | None = Field(None, alias="resolutionSource")
    outcome: list | None = None
    outcome_prices: Json[list[float]] | list[float] | None = Field(None, alias="outcomePrices")

    # Visual representation
    image: str | None = None
    icon: str | None = None

    # Temporal information
    start_date: datetime | None = Field(None, alias="startDate")
    end_date: datetime | None = Field(None, alias="endDate")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime | None = Field(None, alias="updatedAt")
    start_date_iso: datetime | None = Field(None, alias="startDateIso")
    end_date_iso: datetime | None = Field(None, alias="endDateIso")
    deployed_timestamp: datetime | None = Field(None, alias="deployedTimestamp")
    accepting_orders_timestamp: datetime | None = Field(
        None, alias="acceptingOrdersTimestamp",
    )

    # Status flags
    active: bool
    closed: bool
    archived: bool
    new: bool | None = None
    featured: bool | None = None
    restricted: bool
    ready: bool
    deployed: bool | None = None
    funded: bool
    cyom: bool
    approved: bool

    # Financial metrics
    liquidity: float | None = None
    volume: float | None = None
    volume_num: float | None = Field(None, alias="volumeNum")
    liquidity_num: float | None = Field(None, alias="liquidityNum")
    volume_24hr: float | None = Field(None, alias="volume24hr")
    volume_24hr_clob: float | None = Field(None, alias="volume24hrClob")
    volume_clob: float | None = Field(None, alias="volumeClob")
    liquidity_clob: float | None = Field(None, alias="liquidityClob")
    competitive: float | None = None
    spread: float

    # Order book settings
    enable_order_book: bool | None = Field(None, alias="enableOrderBook")
    order_price_min_tick_size: float | None = Field(
        None, alias="orderPriceMinTickSize",
    )
    order_min_size: float | None = Field(None, alias="orderMinSize")
    accepting_orders: bool | None = Field(None, alias="acceptingOrders")

    # Related data
    events: list[Event] | None = None
    clob_rewards: list[ClobReward] | None = Field(None, alias="clobRewards")

    # User interaction
    comment_count: int | None = Field(None, alias="commentCount")

    # Market maker information
    market_maker_address: str = Field(alias="marketMakerAddress")

    # Additional settings
    group_item_title: str | None = Field(None, alias="groupItemTitle")
    group_item_threshold: int | None = Field(None, alias="groupItemThreshold")
    token_ids: Json[list[str]] | list[str] | None = Field(None, alias="clobTokenIds")
    uma_bond: int | None = Field(None, alias="umaBond")
    uma_reward: float | None = Field(None, alias="umaReward")
    neg_risk: bool | None = Field(None, alias="negRisk")
    pager_duty_notification_enabled: bool = Field(alias="pagerDutyNotificationEnabled")
    review_status: str | None = Field(None, alias="reviewStatus")
    rewards_min_size: int = Field(alias="rewardsMinSize")
    rewards_max_spread: float = Field(alias="rewardsMaxSpread")

    # Resolution information
    submitted_by: str | None = None
    resolved_by: EthAddress | None = Field(None, alias="resolvedBy")
    has_reviewed_dates: bool | None = Field(None, alias="hasReviewedDates")

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
    # Basic identification
    id: str
    condition_id: Keccak256 = Field(alias="conditionId")

    # Reward information
    asset_address: str = Field(alias="assetAddress")
    rewards_amount: float = Field(alias="rewardsAmount")
    rewards_daily_rate: float | None = Field(None, alias="rewardsDailyRate")

    # Temporal information
    start_date: datetime = Field(alias="startDate")
    end_date: datetime = Field(alias="endDate")


class Tag(BaseModel):
    # Basic identification
    id: str
    label: str
    slug: str

    # Display settings
    force_show: bool | None = Field(None, alias="forceShow")
    force_hide: bool | None = Field(None, alias="forceHide")

    # Temporal information
    published_at: TimestampWithTZ | datetime | None = Field(None, alias="publishedAt")
    created_at: datetime | None = Field(None, alias="createdAt")
    updated_at: datetime | None = Field(None, alias="updatedAt")

    # User information
    created_by: int | None = Field(None, alias="createdBy")
    updated_by: int | None = Field(None, alias="updatedBy")


class Series(BaseModel):
    # Basic identification
    id: str
    slug: str
    ticker: str
    title: str

    # Series characteristics
    series_type: str | None = Field(None,  alias="seriesType")
    recurrence: str | None = None
    layout: str | None = None

    # Visual representation
    icon: str | None = None
    image: str | None = None

    # Temporal information
    start_date: datetime | None = Field(None, alias="startDate")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime | None = Field(None, alias="updatedAt")
    published_at: TimestampWithTZ | datetime | None = Field(None, alias="publishedAt")

    # Status flags
    active: bool | None = None
    archived: bool | None = None
    closed: bool | None = None
    featured: bool | None = None
    new: bool | None = None
    restricted: bool | None = None

    # Financial metrics
    liquidity: float | None = None
    volume: float | None = None
    volume_24hr: float | None = Field(None, alias="volume24hr")
    competitive: str | None = None

    # User interaction
    comment_count: int = Field(alias="commentCount")
    comments_enabled: bool | None = Field(None, alias="commentsEnabled")

    # User information
    created_by: str | None = Field(None, alias="createdBy")
    updated_by: str | None = Field(None, alias="updatedBy")


class QueryEvent(BaseModel):
    # Basic identification
    id: str
    slug: str
    title: str

    # Visual representation
    image: str | None = None

    # Status flags
    active: bool
    closed: bool
    archived: bool
    neg_risk: bool | None = Field(None, alias="negRisk")

    # Temporal information
    start_date: datetime | None = Field(None, alias="startDate")
    end_date: datetime | None = Field(None, alias="endDate")
    ended: bool

    # Related data
    markets: list[QueryMarket] | None = None


class QueryMarket(BaseModel):
    # Basic identification
    slug: str
    question: str
    group_item_title: str | None = Field(None, alias="groupItemTitle")

    # Market data
    outcomes: list | None = None
    outcome_prices: Json[list[float]] | list[float] | None = Field(None, alias="outcomePrices")
    last_trade_price: float | None = Field(None, alias="lastTradePrice")
    best_ask: float | None = Field(None, alias="bestAsk")
    best_bid: float | None = Field(None, alias="bestBid")
    spread: float

    # Status flags
    closed: bool
    archived: bool
