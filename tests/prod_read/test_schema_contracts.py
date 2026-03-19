from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx
import pytest

from polymarket_apis.testing.contract_assertions import (
    assert_api_contract,
    fail_contract,
    fetch_json,
)
from polymarket_apis.types.clob_types import ClobMarket, OrderBookSummary
from polymarket_apis.types.common import TimeseriesPoint
from polymarket_apis.types.data_types import (
    Activity,
    ClosedPosition,
    EventLiveVolume,
    HolderResponse,
    LeaderboardUser,
    MarketValue,
    Position,
    Trade,
    UserMetric,
    UserRank,
    ValueResponse,
)
from polymarket_apis.types.gamma_types import Event, GammaMarket


@pytest.fixture(scope="module")
def http_client() -> Iterator[httpx.Client]:
    with httpx.Client(http2=True, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="module")
def gamma_markets_payload(http_client: httpx.Client) -> list[dict[str, Any]]:
    payload = fetch_json(
        "gamma /markets",
        http_client,
        "https://gamma-api.polymarket.com/markets",
        params={
            "limit": 5,
            "offset": 0,
            "active": True,
            "closed": False,
            "start_date_min": int(
                (datetime.now(tz=UTC) - timedelta(days=1)).timestamp()
            ),
        },
    )
    if not isinstance(payload, list):
        fail_contract("schema mismatch", "gamma /markets returned a non-list payload.")
    if not payload:
        fail_contract("endpoint unavailable", "gamma /markets returned an empty list.")
    return payload


@pytest.fixture(scope="module")
def gamma_market(gamma_markets_payload: list[dict[str, Any]]) -> GammaMarket:
    markets = cast(
        "list[GammaMarket]",
        assert_api_contract("gamma /markets", list[GammaMarket], gamma_markets_payload),
    )
    return markets[0]


@pytest.fixture(scope="module")
def gamma_events_payload(http_client: httpx.Client) -> list[dict[str, Any]]:
    payload = fetch_json(
        "gamma /events",
        http_client,
        "https://gamma-api.polymarket.com/events",
        params={
            "limit": 5,
            "offset": 0,
            "active": "true",
            "archived": "false",
            "start_date_min": int(
                (datetime.now(tz=UTC) - timedelta(days=1)).timestamp()
            ),
        },
    )
    if not isinstance(payload, list):
        fail_contract("schema mismatch", "gamma /events returned a non-list payload.")
    if not payload:
        fail_contract("endpoint unavailable", "gamma /events returned an empty list.")
    return payload


@pytest.fixture(scope="module")
def gamma_event(gamma_events_payload: list[dict[str, Any]]) -> Event:
    events = cast(
        "list[Event]",
        assert_api_contract("gamma /events", list[Event], gamma_events_payload),
    )
    return events[0]


@pytest.fixture(scope="module")
def leaderboard_payload(http_client: httpx.Client) -> list[dict[str, Any]]:
    payload = fetch_json(
        "data /v1/leaderboard",
        http_client,
        "https://data-api.polymarket.com/v1/leaderboard",
        params={
            "category": "OVERALL",
            "timePeriod": "DAY",
            "orderBy": "VOL",
            "limit": 5,
            "offset": 0,
        },
    )
    if not isinstance(payload, list):
        fail_contract(
            "schema mismatch",
            "data /v1/leaderboard returned a non-list payload.",
        )
    if not payload:
        fail_contract(
            "endpoint unavailable",
            "data /v1/leaderboard returned an empty list.",
        )
    return payload


@pytest.fixture(scope="module")
def leaderboard_user(leaderboard_payload: list[dict[str, Any]]) -> LeaderboardUser:
    users = cast(
        "list[LeaderboardUser]",
        assert_api_contract(
            "data /v1/leaderboard",
            list[LeaderboardUser],
            leaderboard_payload,
        ),
    )
    return users[0]


@pytest.mark.prod_read
def test_gamma_markets_schema(gamma_markets_payload: list[dict[str, Any]]) -> None:
    markets = assert_api_contract(
        "gamma /markets", list[GammaMarket], gamma_markets_payload
    )
    if not markets:
        fail_contract(
            "endpoint unavailable", "gamma /markets produced no validated markets."
        )


@pytest.mark.prod_read
def test_gamma_events_schema(gamma_events_payload: list[dict[str, Any]]) -> None:
    events = assert_api_contract("gamma /events", list[Event], gamma_events_payload)
    if not events:
        fail_contract(
            "endpoint unavailable", "gamma /events produced no validated events."
        )


@pytest.mark.prod_read
def test_clob_market_schema(
    http_client: httpx.Client, gamma_market: GammaMarket
) -> None:
    if not gamma_market.condition_id:
        fail_contract("schema mismatch", "Gamma market is missing condition_id.")
    payload = fetch_json(
        "clob /markets/{condition_id}",
        http_client,
        f"https://clob.polymarket.com/markets/{gamma_market.condition_id}",
    )
    market = assert_api_contract("clob /markets/{condition_id}", ClobMarket, payload)
    if market.condition_id != gamma_market.condition_id:
        fail_contract(
            "schema mismatch",
            "CLOB market condition_id did not match the source Gamma market condition_id.",
        )


@pytest.mark.prod_read
def test_clob_order_book_schema(
    http_client: httpx.Client,
    gamma_market: GammaMarket,
) -> None:
    if not gamma_market.token_ids:
        fail_contract("schema mismatch", "Gamma market is missing token ids.")
    token_ids = gamma_market.token_ids
    payload = fetch_json(
        "clob /book",
        http_client,
        "https://clob.polymarket.com/book",
        params={"token_id": token_ids[0]},
    )
    order_book = assert_api_contract("clob /book", OrderBookSummary, payload)
    if order_book.condition_id != gamma_market.condition_id:
        fail_contract(
            "schema mismatch",
            "CLOB order book condition_id did not match the source Gamma market condition_id.",
        )


@pytest.mark.prod_read
def test_data_positions_schema(
    http_client: httpx.Client,
    leaderboard_user: LeaderboardUser,
) -> None:
    payload = fetch_json(
        "data /positions",
        http_client,
        "https://data-api.polymarket.com/positions",
        params={
            "user": leaderboard_user.proxy_wallet,
            "sizeThreshold": 0,
            "limit": 5,
            "offset": 0,
        },
    )
    positions = assert_api_contract("data /positions", list[Position], payload)
    if not isinstance(positions, list):
        fail_contract("schema mismatch", "data /positions did not validate as a list.")


@pytest.mark.prod_read
def test_data_activity_schema(
    http_client: httpx.Client,
    leaderboard_user: LeaderboardUser,
) -> None:
    payload = fetch_json(
        "data /activity",
        http_client,
        "https://data-api.polymarket.com/activity",
        params={"user": leaderboard_user.proxy_wallet, "limit": 5, "offset": 0},
    )
    activity = assert_api_contract("data /activity", list[Activity], payload)
    if not isinstance(activity, list):
        fail_contract("schema mismatch", "data /activity did not validate as a list.")


@pytest.mark.prod_read
def test_data_trades_schema(
    http_client: httpx.Client,
    gamma_market: GammaMarket,
) -> None:
    if not gamma_market.condition_id:
        fail_contract("schema mismatch", "Gamma market is missing condition_id.")
    payload = fetch_json(
        "data /trades",
        http_client,
        "https://data-api.polymarket.com/trades",
        params={"market": gamma_market.condition_id, "limit": 5, "offset": 0},
    )
    trades = assert_api_contract("data /trades", list[Trade], payload)
    if not isinstance(trades, list):
        fail_contract("schema mismatch", "data /trades did not validate as a list.")


@pytest.mark.prod_read
def test_data_holders_schema(
    http_client: httpx.Client,
    gamma_market: GammaMarket,
) -> None:
    if not gamma_market.condition_id:
        fail_contract("schema mismatch", "Gamma market is missing condition_id.")
    payload = fetch_json(
        "data /holders",
        http_client,
        "https://data-api.polymarket.com/holders",
        params={"market": gamma_market.condition_id, "limit": 5, "min_balance": 1},
    )
    holders = assert_api_contract("data /holders", list[HolderResponse], payload)
    if not isinstance(holders, list):
        fail_contract("schema mismatch", "data /holders did not validate as a list.")


@pytest.mark.prod_read
def test_data_value_schema(
    http_client: httpx.Client,
    leaderboard_user: LeaderboardUser,
) -> None:
    payload = fetch_json(
        "data /value",
        http_client,
        "https://data-api.polymarket.com/value",
        params={"user": leaderboard_user.proxy_wallet},
    )
    values = assert_api_contract("data /value", list[ValueResponse], payload)
    if not values:
        fail_contract("endpoint unavailable", "data /value returned no rows.")


@pytest.mark.prod_read
def test_data_closed_positions_schema(
    http_client: httpx.Client,
    leaderboard_user: LeaderboardUser,
) -> None:
    payload = fetch_json(
        "data /closed-positions",
        http_client,
        "https://data-api.polymarket.com/closed-positions",
        params={"user": leaderboard_user.proxy_wallet},
    )
    positions = assert_api_contract(
        "data /closed-positions", list[ClosedPosition], payload
    )
    if not isinstance(positions, list):
        fail_contract(
            "schema mismatch",
            "data /closed-positions did not validate as a list.",
        )


@pytest.mark.prod_read
def test_data_traded_schema(
    http_client: httpx.Client,
    leaderboard_user: LeaderboardUser,
) -> None:
    payload = fetch_json(
        "data /traded",
        http_client,
        "https://data-api.polymarket.com/traded",
        params={"user": leaderboard_user.proxy_wallet},
    )
    if not isinstance(payload, dict):
        fail_contract("schema mismatch", "data /traded returned a non-object payload.")
    if "traded" not in payload:
        fail_contract(
            "schema mismatch", "data /traded payload is missing the `traded` field."
        )
    if not isinstance(payload["traded"], int):
        fail_contract("schema mismatch", "data /traded `traded` field is not an int.")


@pytest.mark.prod_read
def test_data_open_interest_schema(
    http_client: httpx.Client,
    gamma_market: GammaMarket,
) -> None:
    if not gamma_market.condition_id:
        fail_contract("schema mismatch", "Gamma market is missing condition_id.")
    payload = fetch_json(
        "data /oi",
        http_client,
        "https://data-api.polymarket.com/oi",
        params={"market": gamma_market.condition_id},
    )
    open_interest = assert_api_contract("data /oi", list[MarketValue], payload)
    if not isinstance(open_interest, list):
        fail_contract("schema mismatch", "data /oi did not validate as a list.")


@pytest.mark.prod_read
def test_data_live_volume_schema(
    http_client: httpx.Client,
    gamma_event: Event,
) -> None:
    if gamma_event.id is None:
        fail_contract("schema mismatch", "Gamma event is missing id.")
    payload = fetch_json(
        "data /live-volume",
        http_client,
        "https://data-api.polymarket.com/live-volume",
        params={"id": gamma_event.id},
    )
    live_volume = assert_api_contract(
        "data /live-volume", list[EventLiveVolume], payload
    )
    if not isinstance(live_volume, list):
        fail_contract(
            "schema mismatch", "data /live-volume did not validate as a list."
        )


@pytest.mark.prod_read
def test_user_pnl_schema(
    http_client: httpx.Client,
    leaderboard_user: LeaderboardUser,
) -> None:
    payload = fetch_json(
        "user-pnl /user-pnl",
        http_client,
        "https://user-pnl-api.polymarket.com/user-pnl",
        params={
            "user_address": leaderboard_user.proxy_wallet,
            "interval": "1d",
            "fidelity": "1h",
        },
    )
    points = assert_api_contract("user-pnl /user-pnl", list[TimeseriesPoint], payload)
    if not isinstance(points, list):
        fail_contract(
            "schema mismatch", "user-pnl /user-pnl did not validate as a list."
        )


@pytest.mark.prod_read
def test_lb_profit_schema(
    http_client: httpx.Client,
    leaderboard_user: LeaderboardUser,
) -> None:
    payload = fetch_json(
        "lb-api /profit",
        http_client,
        "https://lb-api.polymarket.com/profit",
        params={"address": leaderboard_user.proxy_wallet, "window": "1d", "limit": 1},
    )
    metrics = assert_api_contract("lb-api /profit", list[UserMetric], payload)
    if not metrics:
        fail_contract("endpoint unavailable", "lb-api /profit returned no rows.")


@pytest.mark.prod_read
def test_lb_rank_schema(
    http_client: httpx.Client,
    leaderboard_user: LeaderboardUser,
) -> None:
    payload = fetch_json(
        "lb-api /rank",
        http_client,
        "https://lb-api.polymarket.com/rank",
        params={
            "address": leaderboard_user.proxy_wallet,
            "window": "1d",
            "rankType": "vol",
        },
    )
    ranks = assert_api_contract("lb-api /rank", list[UserRank], payload)
    if not ranks:
        fail_contract("endpoint unavailable", "lb-api /rank returned no rows.")
