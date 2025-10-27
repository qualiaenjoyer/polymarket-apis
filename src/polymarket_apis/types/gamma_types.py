from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Json,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    field_validator,
)

from .common import EthAddress, FlexibleDatetime, Keccak256


class OptimizedImage(BaseModel):
    """Optimized image data."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="id")
    image_url_source: Optional[str] = Field(None, alias="imageUrlSource")
    image_url_optimized: Optional[str] = Field(None, alias="imageUrlOptimized")
    image_size_kb_source: Optional[int] = Field(None, alias="imageSizeKbSource")
    image_size_kb_optimized: Optional[int] = Field(None, alias="imageSizeKbOptimized")
    image_optimized_complete: Optional[bool] = Field(
        None, alias="imageOptimizedComplete"
    )
    image_optimized_last_updated: Optional[str] = Field(
        None, alias="imageOptimizedLastUpdated"
    )
    rel_id: Optional[int] = Field(None, alias="relID")
    field: Optional[str] = Field(None, alias="field")
    relname: Optional[str] = Field(None, alias="relname")


class GammaMarket(BaseModel):
    """Market model."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="id")
    condition_id: Optional[Keccak256] = Field(None, alias="conditionId")
    question_id: Optional[Keccak256] = Field(None, alias="questionID")
    slug: Optional[str] = Field(None, alias="slug")
    question: Optional[str] = Field(None, alias="question")
    twitter_card_image: Optional[str] = Field(None, alias="twitterCardImage")
    resolution_source: Optional[str] = Field(None, alias="resolutionSource")
    end_date: Optional[datetime] = Field(None, alias="endDate")
    category: Optional[str] = Field(None, alias="category")
    amm_type: Optional[str] = Field(None, alias="ammType")
    liquidity: Optional[float] = Field(None, alias="liquidity")
    sponsor_name: Optional[str] = Field(None, alias="sponsorName")
    sponsor_image: Optional[str] = Field(None, alias="sponsorImage")
    start_date: Optional[datetime] = Field(None, alias="startDate")
    x_axis_value: Optional[str] = Field(None, alias="xAxisValue")
    y_axis_value: Optional[str] = Field(None, alias="yAxisValue")
    denomination_token: Optional[str] = Field(None, alias="denominationToken")
    fee: Optional[str] = Field(None, alias="fee")
    image: Optional[str] = Field(None, alias="image")
    icon: Optional[str] = Field(None, alias="icon")
    lower_bound: Optional[str] = Field(None, alias="lowerBound")
    upper_bound: Optional[str] = Field(None, alias="upperBound")
    description: Optional[str] = Field(None, alias="description")
    outcomes: Optional[str] = Field(None, alias="outcomes")
    outcome_prices: Optional[Json[list[float]] | list[float]] = Field(
        None, alias="outcomePrices"
    )
    volume: Optional[str] = Field(None, alias="volume")
    active: Optional[bool] = Field(None, alias="active")
    market_type: Optional[str] = Field(None, alias="marketType")
    format_type: Optional[str] = Field(None, alias="formatType")
    lower_bound_date: Optional[datetime] = Field(None, alias="lowerBoundDate")
    upper_bound_date: Optional[datetime] = Field(None, alias="upperBoundDate")
    closed: Optional[bool] = Field(None, alias="closed")
    market_maker_address: Optional[str] = Field(None, alias="marketMakerAddress")
    created_by: Optional[int] = Field(None, alias="createdBy")
    updated_by: Optional[int] = Field(None, alias="updatedBy")
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")
    closed_time: Optional[str] = Field(None, alias="closedTime")
    wide_format: Optional[bool] = Field(None, alias="wideFormat")
    new: Optional[bool] = Field(None, alias="new")
    mailchimp_tag: Optional[str] = Field(None, alias="mailchimpTag")
    featured: Optional[bool] = Field(None, alias="featured")
    archived: Optional[bool] = Field(None, alias="archived")
    resolved_by: Optional[EthAddress] = Field(None, alias="resolvedBy")
    restricted: Optional[bool] = Field(None, alias="restricted")
    market_group: Optional[int] = Field(None, alias="marketGroup")
    group_item_title: Optional[str] = Field(None, alias="groupItemTitle")
    group_item_threshold: Optional[str] = Field(None, alias="groupItemThreshold")
    uma_end_date: Optional[FlexibleDatetime] = Field(None, alias="umaEndDate")
    enable_order_book: Optional[bool] = Field(None, alias="enableOrderBook")
    order_price_min_tick_size: Optional[float] = Field(
        None, alias="orderPriceMinTickSize"
    )
    order_min_size: Optional[float] = Field(None, alias="orderMinSize")
    uma_resolution_status: Optional[str] = Field(None, alias="umaResolutionStatus")
    curation_order: Optional[int] = Field(None, alias="curationOrder")
    volume_num: Optional[float] = Field(None, alias="volumeNum")
    liquidity_num: Optional[float] = Field(None, alias="liquidityNum")
    end_date_iso: Optional[datetime] = Field(None, alias="endDateIso")
    start_date_iso: Optional[datetime] = Field(None, alias="startDateIso")
    uma_end_date_iso: Optional[datetime] = Field(None, alias="umaEndDateIso")
    has_reviewed_dates: Optional[bool] = Field(None, alias="hasReviewedDates")
    ready_for_cron: Optional[bool] = Field(None, alias="readyForCron")
    comments_enabled: Optional[bool] = Field(None, alias="commentsEnabled")
    volume_24hr: Optional[float] = Field(None, alias="volume24hr")
    volume_1wk: Optional[float] = Field(None, alias="volume1wk")
    volume_1mo: Optional[float] = Field(None, alias="volume1mo")
    volume_1yr: Optional[float] = Field(None, alias="volume1yr")
    game_start_time: Optional[str] = Field(None, alias="gameStartTime")
    seconds_delay: Optional[int] = Field(None, alias="secondsDelay")
    token_ids: Optional[Json[list[str]] | list[str]] = Field(None, alias="clobTokenIds")
    disqus_thread: Optional[str] = Field(None, alias="disqusThread")
    short_outcomes: Optional[str] = Field(None, alias="shortOutcomes")
    team_a_id: Optional[str] = Field(None, alias="teamAID")
    team_b_id: Optional[str] = Field(None, alias="teamBID")
    uma_bond: Optional[str] = Field(None, alias="umaBond")
    uma_reward: Optional[str] = Field(None, alias="umaReward")
    fpmm_live: Optional[bool] = Field(None, alias="fpmmLive")
    volume_24hr_amm: Optional[float] = Field(None, alias="volume24hrAmm")
    volume_1wk_amm: Optional[float] = Field(None, alias="volume1wkAmm")
    volume_1mo_amm: Optional[float] = Field(None, alias="volume1moAmm")
    volume_1yr_amm: Optional[float] = Field(None, alias="volume1yrAmm")
    volume_24hr_clob: Optional[float] = Field(None, alias="volume24hrClob")
    volume_1wk_clob: Optional[float] = Field(None, alias="volume1wkClob")
    volume_1mo_clob: Optional[float] = Field(None, alias="volume1moClob")
    volume_1yr_clob: Optional[float] = Field(None, alias="volume1yrClob")
    volume_amm: Optional[float] = Field(None, alias="volumeAmm")
    volume_clob: Optional[float] = Field(None, alias="volumeClob")
    liquidity_amm: Optional[float] = Field(None, alias="liquidityAmm")
    liquidity_clob: Optional[float] = Field(None, alias="liquidityClob")
    maker_base_fee: Optional[int] = Field(None, alias="makerBaseFee")
    taker_base_fee: Optional[int] = Field(None, alias="takerBaseFee")
    custom_liveness: Optional[int] = Field(None, alias="customLiveness")
    accepting_orders: Optional[bool] = Field(None, alias="acceptingOrders")
    notifications_enabled: Optional[bool] = Field(None, alias="notificationsEnabled")
    score: Optional[int] = Field(None, alias="score")
    image_optimized: Optional[OptimizedImage] = Field(None, alias="imageOptimized")
    icon_optimized: Optional[OptimizedImage] = Field(None, alias="iconOptimized")
    events: Optional[list[Event]] = None
    categories: Optional[list[Category]] = Field(None, alias="categories")
    tags: Optional[list[Tag]] = Field(None, alias="tags")
    creator: Optional[str] = Field(None, alias="creator")
    ready: Optional[bool] = Field(None, alias="ready")
    funded: Optional[bool] = Field(None, alias="funded")
    past_slugs: Optional[str] = Field(None, alias="pastSlugs")
    ready_timestamp: Optional[datetime] = Field(None, alias="readyTimestamp")
    funded_timestamp: Optional[datetime] = Field(None, alias="fundedTimestamp")
    accepting_orders_timestamp: Optional[datetime] = Field(
        None, alias="acceptingOrdersTimestamp"
    )
    competitive: Optional[float] = Field(None, alias="competitive")
    rewards_min_size: Optional[float] = Field(None, alias="rewardsMinSize")
    rewards_max_spread: Optional[float] = Field(None, alias="rewardsMaxSpread")
    spread: Optional[float] = Field(None, alias="spread")
    automatically_resolved: Optional[bool] = Field(None, alias="automaticallyResolved")
    one_day_price_change: Optional[float] = Field(None, alias="oneDayPriceChange")
    one_hour_price_change: Optional[float] = Field(None, alias="oneHourPriceChange")
    one_week_price_change: Optional[float] = Field(None, alias="oneWeekPriceChange")
    one_month_price_change: Optional[float] = Field(None, alias="oneMonthPriceChange")
    one_year_price_change: Optional[float] = Field(None, alias="oneYearPriceChange")
    last_trade_price: Optional[float] = Field(None, alias="lastTradePrice")
    best_bid: Optional[float] = Field(None, alias="bestBid")
    best_ask: Optional[float] = Field(None, alias="bestAsk")
    automatically_active: Optional[bool] = Field(None, alias="automaticallyActive")
    clear_book_on_start: Optional[bool] = Field(None, alias="clearBookOnStart")
    chart_color: Optional[str] = Field(None, alias="chartColor")
    series_color: Optional[str] = Field(None, alias="seriesColor")
    show_gmp_series: Optional[bool] = Field(None, alias="showGmpSeries")
    show_gmp_outcome: Optional[bool] = Field(None, alias="showGmpOutcome")
    manual_activation: Optional[bool] = Field(None, alias="manualActivation")
    neg_risk_other: Optional[bool] = Field(None, alias="negRiskOther")
    game_id: Optional[str] = Field(None, alias="gameId")
    group_item_range: Optional[str] = Field(None, alias="groupItemRange")
    sports_market_type: Optional[str] = Field(None, alias="sportsMarketType")
    line: Optional[float] = Field(None, alias="line")
    uma_resolution_statuses: Optional[str] = Field(None, alias="umaResolutionStatuses")
    pending_deployment: Optional[bool] = Field(None, alias="pendingDeployment")
    deploying: Optional[bool] = Field(None, alias="deploying")
    deploying_timestamp: Optional[datetime] = Field(None, alias="deployingTimestamp")
    scheduled_deployment_timestamp: Optional[datetime] = Field(
        None, alias="scheduledDeploymentTimestamp"
    )
    rfq_enabled: Optional[bool] = Field(None, alias="rfqEnabled")
    event_start_time: Optional[datetime] = Field(None, alias="eventStartTime")
    clob_rewards: Optional[list[ClobReward]] = Field(None, alias="clobRewards")
    submitted_by: Optional[str] = None
    approved: Optional[bool] = None
    pager_duty_notification_enabled: Optional[bool] = Field(
        None, alias="pagerDutyNotificationEnabled"
    )
    holding_rewards_enabled: Optional[bool] = Field(None, alias="holdingRewardsEnabled")
    fees_enabled: Optional[bool] = Field(None, alias="feesEnabled")
    cyom: Optional[bool] = Field(None, alias="cyom")

    @field_validator("condition_id", mode="wrap")
    @classmethod
    def validate_condition_id(
        cls,
        value: str,
        handler: ValidatorFunctionWrapHandler,
        info: ValidationInfo,
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


class Series(BaseModel):
    """Series model."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="id")
    ticker: Optional[str] = Field(None, alias="ticker")
    slug: Optional[str] = Field(None, alias="slug")
    title: Optional[str] = Field(None, alias="title")
    subtitle: Optional[str] = Field(None, alias="subtitle")
    series_type: Optional[str] = Field(None, alias="seriesType")
    recurrence: Optional[str] = Field(None, alias="recurrence")
    description: Optional[str] = Field(None, alias="description")
    image: Optional[str] = Field(None, alias="image")
    icon: Optional[str] = Field(None, alias="icon")
    layout: Optional[str] = Field(None, alias="layout")
    active: Optional[bool] = Field(None, alias="active")
    closed: Optional[bool] = Field(None, alias="closed")
    archived: Optional[bool] = Field(None, alias="archived")
    new: Optional[bool] = Field(None, alias="new")
    featured: Optional[bool] = Field(None, alias="featured")
    restricted: Optional[bool] = Field(None, alias="restricted")
    is_template: Optional[bool] = Field(None, alias="isTemplate")
    template_variables: Optional[bool] = Field(None, alias="templateVariables")
    published_at: Optional[FlexibleDatetime] = Field(None, alias="publishedAt")
    created_by: Optional[str] = Field(None, alias="createdBy")
    updated_by: Optional[str] = Field(None, alias="updatedBy")
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")
    comments_enabled: Optional[bool] = Field(None, alias="commentsEnabled")
    competitive: Optional[str] = Field(None, alias="competitive")
    volume_24hr: Optional[float] = Field(None, alias="volume24hr")
    volume: Optional[float] = Field(None, alias="volume")
    liquidity: Optional[float] = Field(None, alias="liquidity")
    start_date: Optional[datetime] = Field(None, alias="startDate")
    pyth_token_id: Optional[str] = Field(None, alias="pythTokenID")
    cg_asset_name: Optional[str] = Field(None, alias="cgAssetName")
    score: Optional[int] = Field(None, alias="score")
    events: Optional[list[Event]] = Field(None, alias="events")
    collections: Optional[list[Collection]] = Field(None, alias="collections")
    categories: Optional[list[Category]] = Field(None, alias="categories")
    tags: Optional[list[Tag]] = Field(None, alias="tags")
    comment_count: Optional[int] = Field(None, alias="commentCount")
    chats: Optional[list[Chat]] = Field(None, alias="chats")


class Category(BaseModel):
    """Category model."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="id")
    label: Optional[str] = Field(None, alias="label")
    parent_category: Optional[str] = Field(None, alias="parentCategory")
    slug: Optional[str] = Field(None, alias="slug")
    published_at: Optional[str] = Field(None, alias="publishedAt")
    created_by: Optional[str] = Field(None, alias="createdBy")
    updated_by: Optional[str] = Field(None, alias="updatedBy")
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")


class Tag(BaseModel):
    """Tag model."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="id")
    label: Optional[str] = Field(None, alias="label")
    slug: Optional[str] = Field(None, alias="slug")
    force_show: Optional[bool] = Field(None, alias="forceShow")
    published_at: Optional[str] = Field(None, alias="publishedAt")
    created_by: Optional[int] = Field(None, alias="createdBy")
    updated_by: Optional[int] = Field(None, alias="updatedBy")
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")
    force_hide: Optional[bool] = Field(None, alias="forceHide")
    is_carousel: Optional[bool] = Field(None, alias="isCarousel")


class TagRelation(BaseModel):
    """Tag relation model."""

    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(alias="id")
    tag_id: int = Field(alias="tagID")
    related_tag_id: int = Field(alias="relatedTagID")
    rank: int


class Chat(BaseModel):
    """Chat model."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="id")
    channel_id: Optional[str] = Field(None, alias="channelId")
    channel_name: Optional[str] = Field(None, alias="channelName")
    channel_image: Optional[str] = Field(None, alias="channelImage")
    live: Optional[bool] = Field(None, alias="live")
    start_time: Optional[datetime] = Field(None, alias="startTime")
    end_time: Optional[datetime] = Field(None, alias="endTime")


class Collection(BaseModel):
    """Collection model."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="id")
    ticker: Optional[str] = Field(None, alias="ticker")
    slug: Optional[str] = Field(None, alias="slug")
    title: Optional[str] = Field(None, alias="title")
    subtitle: Optional[str] = Field(None, alias="subtitle")
    collection_type: Optional[str] = Field(None, alias="collectionType")
    description: Optional[str] = Field(None, alias="description")
    tags: Optional[str] = Field(None, alias="tags")
    image: Optional[str] = Field(None, alias="image")
    icon: Optional[str] = Field(None, alias="icon")
    header_image: Optional[str] = Field(None, alias="headerImage")
    layout: Optional[str] = Field(None, alias="layout")
    active: Optional[bool] = Field(None, alias="active")
    closed: Optional[bool] = Field(None, alias="closed")
    archived: Optional[bool] = Field(None, alias="archived")
    new: Optional[bool] = Field(None, alias="new")
    featured: Optional[bool] = Field(None, alias="featured")
    restricted: Optional[bool] = Field(None, alias="restricted")
    is_template: Optional[bool] = Field(None, alias="isTemplate")
    template_variables: Optional[str] = Field(None, alias="templateVariables")
    published_at: Optional[str] = Field(None, alias="publishedAt")
    created_by: Optional[str] = Field(None, alias="createdBy")
    updated_by: Optional[str] = Field(None, alias="updatedBy")
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")
    comments_enabled: Optional[bool] = Field(None, alias="commentsEnabled")
    image_optimized: Optional[OptimizedImage] = Field(None, alias="imageOptimized")
    icon_optimized: Optional[OptimizedImage] = Field(None, alias="iconOptimized")
    header_image_optimized: Optional[OptimizedImage] = Field(
        None, alias="headerImageOptimized"
    )


class Creator(BaseModel):
    """Event Creator model."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="id")
    creator_name: Optional[str] = Field(None, alias="creatorName")
    creator_handle: Optional[str] = Field(None, alias="creatorHandle")
    creator_url: Optional[str] = Field(None, alias="creatorUrl")
    creator_image: Optional[str] = Field(None, alias="creatorImage")
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")


class Template(BaseModel):
    """Template model."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="id")
    event_title: Optional[str] = Field(None, alias="eventTitle")
    event_slug: Optional[str] = Field(None, alias="eventSlug")
    event_image: Optional[str] = Field(None, alias="eventImage")
    market_title: Optional[str] = Field(None, alias="marketTitle")
    description: Optional[str] = Field(None, alias="description")
    resolution_source: Optional[str] = Field(None, alias="resolutionSource")
    neg_risk: Optional[bool] = Field(None, alias="negRisk")
    sort_by: Optional[str] = Field(None, alias="sortBy")
    show_market_images: Optional[bool] = Field(None, alias="showMarketImages")
    series_slug: Optional[str] = Field(None, alias="seriesSlug")
    outcomes: Optional[str] = Field(None, alias="outcomes")


class ClobReward(BaseModel):
    """Reward model."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    condition_id: Keccak256 = Field(alias="conditionId")
    asset_address: str = Field(alias="assetAddress")
    rewards_amount: float = Field(alias="rewardsAmount")
    rewards_daily_rate: Optional[float] = Field(None, alias="rewardsDailyRate")
    start_date: datetime = Field(alias="startDate")
    end_date: datetime = Field(alias="endDate")


class Team(BaseModel):
    """Team model."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str
    league: str
    record: Optional[str] = None
    logo: str
    abbreviation: str
    alias: Optional[str] = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")


class Sport(BaseModel):
    """Sport model."""

    model_config = ConfigDict(populate_by_name=True)

    sport: str
    image: Optional[str] = None
    resolution: Optional[str] = None
    ordering: Optional[Literal["home", "away"]] = None
    tags: Optional[list[int]] = None
    series: Optional[int] = None

    @field_validator("tags", mode="before")
    @classmethod
    def split_string_to_int_list(cls, v):
        if isinstance(v, str):
            return [int(i) for i in v.split(",")]
        return v


class Event(BaseModel):
    """Event model."""

    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(alias="id")
    ticker: Optional[str] = Field(None, alias="ticker")
    slug: Optional[str] = Field(None, alias="slug")
    title: Optional[str] = Field(None, alias="title")
    subtitle: Optional[str] = Field(None, alias="subtitle")
    description: Optional[str] = Field(None, alias="description")
    resolution_source: Optional[str] = Field(None, alias="resolutionSource")
    start_date: Optional[datetime] = Field(None, alias="startDate")
    creation_date: Optional[datetime] = Field(None, alias="creationDate")
    end_date: Optional[datetime] = Field(None, alias="endDate")
    image: Optional[str] = Field(None, alias="image")
    icon: Optional[str] = Field(None, alias="icon")
    active: Optional[bool] = Field(None, alias="active")
    closed: Optional[bool] = Field(None, alias="closed")
    archived: Optional[bool] = Field(None, alias="archived")
    new: Optional[bool] = Field(None, alias="new")
    featured: Optional[bool] = Field(None, alias="featured")
    restricted: Optional[bool] = Field(None, alias="restricted")
    liquidity: Optional[float] = Field(None, alias="liquidity")
    volume: Optional[float] = Field(None, alias="volume")
    open_interest: Optional[int] = Field(None, alias="openInterest")
    sort_by: Optional[str] = Field(None, alias="sortBy")
    category: Optional[str] = Field(None, alias="category")
    subcategory: Optional[str] = Field(None, alias="subcategory")
    is_template: Optional[bool] = Field(None, alias="isTemplate")
    template_variables: Optional[str] = Field(None, alias="templateVariables")
    published_at: Optional[FlexibleDatetime] = Field(None, alias="publishedAt")
    created_by: Optional[str] = Field(None, alias="createdBy")
    updated_by: Optional[str] = Field(None, alias="updatedBy")
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")
    comments_enabled: Optional[bool] = Field(None, alias="commentsEnabled")
    competitive: Optional[float] = Field(None, alias="competitive")
    volume_24hr: Optional[float] = Field(None, alias="volume24hr")
    volume_1wk: Optional[float] = Field(None, alias="volume1wk")
    volume_1mo: Optional[float] = Field(None, alias="volume1mo")
    volume_1yr: Optional[float] = Field(None, alias="volume1yr")
    featured_image: Optional[str] = Field(None, alias="featuredImage")
    disqus_thread: Optional[str] = Field(None, alias="disqusThread")
    parent_event: Optional[str] = Field(None, alias="parentEvent")
    enable_order_book: Optional[bool] = Field(None, alias="enableOrderBook")
    liquidity_amm: Optional[float] = Field(None, alias="liquidityAmm")
    liquidity_clob: Optional[float] = Field(None, alias="liquidityClob")
    neg_risk: Optional[bool] = Field(None, alias="negRisk")
    neg_risk_augmented: Optional[bool] = Field(None, alias="negRiskAugmented")
    neg_risk_market_id: Optional[str] = Field(None, alias="negRiskMarketID")
    neg_risk_fee_bips: Optional[int] = Field(None, alias="negRiskFeeBips")
    comment_count: Optional[int] = Field(None, alias="commentCount")
    image_optimized: Optional[OptimizedImage] = Field(None, alias="imageOptimized")
    icon_optimized: Optional[OptimizedImage] = Field(None, alias="iconOptimized")
    featured_image_optimized: Optional[OptimizedImage] = Field(
        None, alias="featuredImageOptimized"
    )
    sub_events: Optional[list[str]] = Field(None, alias="subEvents")
    markets: Optional[list[GammaMarket]] = Field(None, alias="markets")
    series: Optional[list[Series]] = Field(None, alias="series")
    categories: Optional[list[Category]] = Field(None, alias="categories")
    collections: Optional[list[Collection]] = Field(None, alias="collections")
    tags: Optional[list[Tag]] = Field(None, alias="tags")
    cyom: Optional[bool] = Field(None, alias="cyom")
    closed_time: Optional[datetime] = Field(None, alias="closedTime")
    show_all_outcomes: Optional[bool] = Field(None, alias="showAllOutcomes")
    show_market_images: Optional[bool] = Field(None, alias="showMarketImages")
    automatically_resolved: Optional[bool] = Field(None, alias="automaticallyResolved")
    enable_neg_risk: Optional[bool] = Field(None, alias="enableNegRisk")
    automatically_active: Optional[bool] = Field(None, alias="automaticallyActive")
    event_date: Optional[datetime] = Field(None, alias="eventDate")
    start_time: Optional[datetime] = Field(None, alias="startTime")
    event_week: Optional[int] = Field(None, alias="eventWeek")
    series_slug: Optional[str] = Field(None, alias="seriesSlug")
    score: Optional[str] = Field(None, alias="score")
    elapsed: Optional[str] = Field(None, alias="elapsed")
    period: Optional[str] = Field(None, alias="period")
    live: Optional[bool] = Field(None, alias="live")
    ended: Optional[bool] = Field(None, alias="ended")
    finished_timestamp: Optional[datetime] = Field(None, alias="finishedTimestamp")
    gmp_chart_mode: Optional[str] = Field(None, alias="gmpChartMode")
    event_creators: Optional[list[Creator]] = Field(None, alias="eventCreators")
    tweet_count: Optional[int] = Field(None, alias="tweetCount")
    chats: Optional[list[Chat]] = Field(None, alias="chats")
    featured_order: Optional[int] = Field(None, alias="featuredOrder")
    estimate_value: Optional[bool] = Field(None, alias="estimateValue")
    cant_estimate: Optional[bool] = Field(None, alias="cantEstimate")
    estimated_value: Optional[str] = Field(None, alias="estimatedValue")
    templates: Optional[list[Template]] = Field(None, alias="templates")
    spreads_main_line: Optional[float] = Field(None, alias="spreadsMainLine")
    totals_main_line: Optional[float] = Field(None, alias="totalsMainLine")
    carousel_map: Optional[str] = Field(None, alias="carouselMap")
    pending_deployment: Optional[bool] = Field(None, alias="pendingDeployment")
    deploying: Optional[bool] = Field(None, alias="deploying")
    deploying_timestamp: Optional[datetime] = Field(None, alias="deployingTimestamp")
    scheduled_deployment_timestamp: Optional[datetime] = Field(
        None, alias="scheduledDeploymentTimestamp"
    )
    game_status: Optional[str] = Field(None, alias="gameStatus")


class ProfilePosition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    token_id: int = Field(alias="tokenId")
    size: Optional[float] = Field(None, alias="positionSize")

    @field_validator("size", mode="before")
    @classmethod
    def normalize_size(cls, v) -> float:
        if isinstance(v, str):
            return int(v) / 10**6
        return v


class Profile(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = None
    pseudonym: Optional[str] = None
    display_username_public: Optional[bool] = Field(None, alias="displayUsernamePublic")
    proxy_wallet: Optional[EthAddress] = Field(None, alias="proxyWallet")
    base_address: Optional[EthAddress] = Field(None, alias="baseAddress")
    profile_image: Optional[str] = Field(None, alias="profileImage")
    positions: Optional[list[ProfilePosition]] = Field(None, alias="positions")


class Comment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    body: str
    parent_entity_type: Literal["Event", "Series", "market"] = Field(
        alias="parentEntityType"
    )
    parent_entity_id: int = Field(alias="parentEntityID")
    parent_comment_id: Optional[str] = Field(None, alias="parentCommentID")
    user_address: str = Field(alias="userAddress")
    reply_address: Optional[str] = Field(None, alias="replyAddress")
    created_at: datetime = Field(alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")
    profile: Optional[Profile] = None
    reactions: Optional[list[Reaction]] = None
    report_count: Optional[int] = Field(None, alias="reportCount")
    reaction_count: Optional[int] = Field(None, alias="reactionCount")


class Reaction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    comment_id: int = Field(alias="commentID")
    reaction_type: str = Field(alias="reactionType")
    icon: Optional[str] = None
    user_address: str = Field(alias="userAddress")
    created_at: datetime = Field(alias="createdAt")
    profile: Optional[Profile] = None


class Pagination(BaseModel):
    has_more: bool = Field(alias="hasMore")
    total_results: int = Field(alias="totalResults")


class SearchResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    events: Optional[list[Event]] = None
    tags: Optional[list[Tag]] = None
    profiles: Optional[list[Profile]] = None
    pagination: Pagination


Event.model_rebuild()
Series.model_rebuild()
GammaMarket.model_rebuild()
SearchResult.model_rebuild()
