import json
import random
import string
from datetime import datetime
from typing import Literal, Optional, Union
from urllib.parse import urljoin

import httpx

from ..types.gamma_types import Event, EventList, GammaMarket


def generate_random_id(length=16):
    characters = string.ascii_letters + string.digits
    random_id = "".join(random.choices(characters, k=length))
    return random_id


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
        archived: Optional[bool] = None,
        active: Optional[bool] = None,
        closed: Optional[bool] = None,
        slugs: Optional[list[str]] = None,
        market_ids: Optional[list[int]] = None,
        token_ids: Optional[list[str]] = None,
        condition_ids: Optional[list[str]] = None,
        tag_id: Optional[int] = None,
        related_tags: Optional[bool] = False,
        liquidity_num_min: Optional[float] = None,
        liquidity_num_max: Optional[float] = None,
        volume_num_min: Optional[float] = None,
        volume_num_max: Optional[float] = None,
        start_date_min: Optional[datetime] = None,
        start_date_max: Optional[datetime] = None,
        end_date_min: Optional[datetime] = None,
        end_date_max: Optional[datetime] = None,
    ) -> list[GammaMarket]:
        params = {}
        if limit:
            params["limit"] = limit
        if offset:
            params["offset"] = offset
        if order:
            params["order"] = order
            params["ascending"] = ascending
        if slugs:
            params["slug"] = slugs
        if archived is not None:
            params["archived"] = archived
        if active is not None:
            params["active"] = active
        if closed is not None:
            params["closed"] = closed
        if market_ids:
            params["id"] = market_ids
        if token_ids:
            params["clob_token_ids"] = token_ids
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
        return [GammaMarket(**market) for market in response.json()]

    def get_market(self, market_id: str) -> GammaMarket:
        """Get a GammaMarket by market_id."""
        response = self.client.get(self._build_url(f"/markets/{market_id}"))
        response.raise_for_status()
        return GammaMarket(**response.json())

    def get_events(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order: Optional[str] = None,
        ascending: bool = True,
        event_ids: Optional[Union[str, list[str]]] = None,
        slugs: Optional[list[str]] = None,
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
    ) -> list[Event]:
        params = {}
        if limit:
            params["limit"] = limit
        if offset:
            params["offset"] = offset
        if order:
            params["order"] = order
            params["ascending"] = ascending
        if event_ids:
            params["id"] = event_ids
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

    def get_all_events(
        self,
        order: Optional[str] = None,
        ascending: bool = True,
        event_ids: Optional[Union[str, list[str]]] = None,
        slugs: Optional[list[str]] = None,
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
    ) -> list[Event]:
        offset = 0
        events = []

        while True:
            part = self.get_events(
                limit=500,
                offset=offset,
                order=order,
                ascending=ascending,
                event_ids=event_ids,
                slugs=slugs,
                archived=archived,
                active=active,
                closed=closed,
                liquidity_min=liquidity_min,
                liquidity_max=liquidity_max,
                volume_min=volume_min,
                volume_max=volume_max,
                start_date_min=start_date_min,
                start_date_max=start_date_max,
                end_date_min=end_date_min,
                end_date_max=end_date_max,
                tag=tag,
                tag_id=tag_id,
                tag_slug=tag_slug,
                related_tags=related_tags,
            )
            events.extend(part)

            if len(part) < 500:
                break

            offset += 500

        return events

    def search_events(
        self,
        query: str,
        active: bool = True,
        status: Optional[Literal["active", "resolved"]] = "active",
        sort: Literal[
            "volume",
            "volume_24hr",
            "liquidity",
            "start_date",
            "end_date",
            "competitive",
        ] = "volume_24hr",
        page: int = 1,
        limit_per_type: int = 50,  # max is 50
        presets: Optional[
            Literal["EventsHybrid", "EventsTitle"]
            | list[Literal["EventsHybrid", "EventsTitle"]]
        ] = None,
    ) -> EventList:
        """Search for events by query. Should emulate the website search function."""
        params = {
            "q": query,
            "page": page,
            "limit_per_type": limit_per_type,
            "events_status": status,
            "active": active,
        }
        if sort:
            params["sort"] = sort
        if sort == "end_date":
            params["ascending"] = "true"
        if presets:
            params["presets"] = presets
        response = self.client.get(self._build_url("/public-search"), params=params)
        response.raise_for_status()
        return EventList(**response.json())

    def grok_event_summary(self, event_slug: str):
        json_payload = {
            "id": generate_random_id(),
            "messages": [{"role": "user", "content": "", "parts": []}],
        }

        params = {
            "prompt": event_slug,
        }

        with self.client.stream(
            method="POST",
            url="https://polymarket.com/api/grok/event-summary",
            params=params,
            json=json_payload,
        ) as stream:
            messages = []
            citations = []
            seen_urls = set()

            for line_bytes in stream.iter_lines():
                line = (
                    line_bytes.decode() if isinstance(line_bytes, bytes) else line_bytes
                )
                if line.startswith("__SOURCES__:"):
                    sources_json_str = line[len("__SOURCES__:") :]
                    try:
                        sources_obj = json.loads(sources_json_str)
                        for source in sources_obj.get("sources", []):
                            url = source.get("url")
                            if url and url not in seen_urls:
                                citations.append(source)
                                seen_urls.add(url)
                    except json.JSONDecodeError:
                        pass
                else:
                    messages.append(line)
                    print(line, end="")  # or handle message text as needed

        # After reading streamed lines:
        if citations:
            print("\n\nSources:")
            for source in citations:
                print(f"- {source.get('url', 'Unknown URL')}")

    def grok_election_market_explanation(
        self, candidate_name: str, election_title: str
    ):
        text = f"Provide candidate information for {candidate_name} in the {election_title} on Polymarket."
        json_payload = {
            "id": generate_random_id(),
            "messages": [
                {
                    "role": "user",
                    "content": text,
                    "parts": [{"type": "text", "text": text}],
                },
            ],
        }

        response = self.client.post(
            url="https://polymarket.com/api/grok/election-market-explanation",
            json=json_payload,
        )
        response.raise_for_status()

        parts = [p.strip() for p in response.text.split("**") if p.strip()]
        for i, part in enumerate(parts):
            if ":" in part and i != 0:
                print()
            print(part)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()
