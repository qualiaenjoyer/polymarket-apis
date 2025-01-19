from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin

import httpx

from ..types.gamma_types import Event, Market


class PolymarketGammaClient:
    def __init__(self, base_url: str = "https://gamma-api.polymarket.com"):
        self.base_url = base_url
        self.client = httpx.Client(http2=True, timeout=30.0)

    def _build_url(self, endpoint: str) -> str:
        return urljoin(self.base_url, endpoint)

    def get_markets(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order: Optional[str] = None,
        ascending: bool = True,
        ids: Optional[List[int]] = None,
        slugs: Optional[List[str]] = None,
        archived: Optional[bool] = None,
        active: Optional[bool] = None,
        closed: Optional[bool] = None,
        clob_token_ids: Optional[List[str]] = None,
        condition_ids: Optional[List[str]] = None,
        liquidity_num_min: Optional[float] = None,
        liquidity_num_max: Optional[float] = None,
        volume_num_min: Optional[float] = None,
        volume_num_max: Optional[float] = None,
        start_date_min: Optional[datetime] = None,
        start_date_max: Optional[datetime] = None,
        end_date_min: Optional[datetime] = None,
        end_date_max: Optional[datetime] = None,
        tag_id: Optional[int] = None,
        related_tags: bool = False,
    ) -> List[Market]:
        params = {}
        if limit:
            params["limit"] = limit
        if offset:
            params["offset"] = offset
        if order:
            params["order"] = order
            params["ascending"] = ascending
        if ids:
            params["id"] = ids
        if slugs:
            params["slug"] = slugs
        if archived is not None:
            params["archived"] = archived
        if active is not None:
            params["active"] = active
        if closed is not None:
            params["closed"] = closed
        if clob_token_ids:
            params["clob_token_ids"] = clob_token_ids
        if condition_ids:
            params["condition_ids"] = condition_ids
        if liquidity_num_min:
            params["liquidity_num_min"] = liquidity_num_min
        if liquidity_num_max:
            params["liquidity_num_max"] = liquidity_num_max
        if volume_num_min:
            params["volume_num_min"] = volume_num_min
        if volume_num_max:
            params["volume_num_max"] = volume_num_max
        if start_date_min:
            params["start_date_min"] = start_date_min.isoformat()
        if start_date_max:
            params["start_date_max"] = start_date_max.isoformat()
        if end_date_min:
            params["end_date_min"] = end_date_min.isoformat()
        if end_date_max:
            params["end_date_max"] = end_date_max.isoformat()
        if tag_id:
            params["tag_id"] = tag_id
            if related_tags:
                params["related_tags"] = related_tags

        response = self.client.get(self._build_url("/markets"), params=params)
        response.raise_for_status()
        return [Market(**market) for market in response.json()]

    def get_market(self, market_id: int) -> Market:
        response = self.client.get(self._build_url(f"/markets/{market_id}"))
        response.raise_for_status()
        return Market(**response.json())

    def get_events(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order: Optional[str] = None,
        ascending: bool = True,
        ids: Optional[List[int]] = None,
        slugs: Optional[List[str]] = None,
        archived: Optional[bool] = None,
        active: Optional[bool] = None,
        closed: Optional[bool] = None,
        liquidity_min: Optional[float] = None,
        liquidity_max: Optional[float] = None,
        volume_min: Optional[float] = None,
        volume_max: Optional[float] = None,
        start_date_min: Optional[datetime] = None,
        start_date_max: Optional[datetime] = None,
        end_date_min: Optional[datetime] = None,
        end_date_max: Optional[datetime] = None,
        tag: Optional[str] = None,
        tag_id: Optional[int] = None,
        tag_slug: Optional[str] = None,
        related_tags: bool = False,
    ) -> List[Event]:
        params = {}
        if limit:
            params["limit"] = limit
        if offset:
            params["offset"] = offset
        if order:
            params["order"] = order
            params["ascending"] = ascending
        if ids:
            params["id"] = ids
        if slugs:
            params["slug"] = slugs
        if archived is not None:
            params["archived"] = archived
        if active is not None:
            params["active"] = active
        if closed is not None:
            params["closed"] = closed
        if liquidity_min:
            params["liquidity_min"] = liquidity_min
        if liquidity_max:
            params["liquidity_max"] = liquidity_max
        if volume_min:
            params["volume_min"] = volume_min
        if volume_max:
            params["volume_max"] = volume_max
        if start_date_min:
            params["start_date_min"] = start_date_min.isoformat()
        if start_date_max:
            params["start_date_max"] = start_date_max.isoformat()
        if end_date_min:
            params["end_date_min"] = end_date_min.isoformat()
        if end_date_max:
            params["end_date_max"] = end_date_max.isoformat()
        if tag:
            params["tag"] = tag
        elif tag_id:
            params["tag_id"] = tag_id
            if related_tags:
                params["related_tags"] = related_tags
        elif tag_slug:
            params["tag_slug"] = tag_slug

        response = self.client.get(self._build_url("/events"), params=params)
        response.raise_for_status()
        return [Event(**event) for event in response.json()]

    def get_event(self, event_id: int) -> Event:
        response = self.client.get(self._build_url(f"/events/{event_id}"))
        response.raise_for_status()
        return Event(**response.json())

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()
