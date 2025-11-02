import json
import random
import string
from datetime import datetime
from typing import Literal, Optional, Union
from urllib.parse import urljoin

import httpx

from ..types.common import EthAddress
from ..types.gamma_types import (
    Comment,
    Event,
    GammaMarket,
    SearchResult,
    Series,
    Sport,
    Tag,
    TagRelation,
    Team,
)


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

    def search(
        self,
        query: str,
        cache: Optional[bool] = None,
        status: Optional[Literal["active", "resolved"]] = None,
        limit_per_type: Optional[int] = None,  # max is 50
        page: Optional[int] = None,
        tags: Optional[list[str]] = None,
        keep_closed_markets: Optional[bool] = None,
        sort: Optional[
            Literal[
                "volume",
                "volume_24hr",
                "liquidity",
                "start_date",
                "end_date",
                "competitive",
            ]
        ] = None,
        ascending: Optional[bool] = None,
        search_tags: Optional[bool] = None,
        search_profiles: Optional[bool] = None,
        recurrence: Optional[
            Literal["hourly", "daily", "weekly", "monthly", "annual"]
        ] = None,
        exclude_tag_ids: Optional[list[int]] = None,
        optimized: Optional[bool] = None,
    ) -> SearchResult:
        params: dict[str, str | list[str] | int | bool] = {
            "q": query,
        }
        if cache is not None:
            params["cache"] = str(cache).lower()
        if status:
            params["events_status"] = status
        if limit_per_type:
            params["limit_per_type"] = limit_per_type
        if page:
            params["page"] = page
        if tags:
            params["events_tag"] = json.dumps([json.dumps(item) for item in tags])
        if keep_closed_markets is not None:
            params["keep_closed_markets"] = keep_closed_markets
        if sort:
            params["sort"] = sort
        if ascending is not None:
            params["ascending"] = str(ascending).lower()
        if search_tags is not None:
            params["search_tags"] = str(search_tags).lower()
        if search_profiles is not None:
            params["search_profiles"] = str(search_profiles).lower()
        if recurrence:
            params["recurrence"] = recurrence
        if exclude_tag_ids:
            params["exclude_tag_id"] = [str(i) for i in exclude_tag_ids]
        if optimized is not None:
            params["optimized"] = str(optimized).lower()
        response = self.client.get(self._build_url("/public-search"), params=params)
        response.raise_for_status()
        return SearchResult(**response.json())

    def get_market(self, market_id: str) -> GammaMarket:
        """Get a GammaMarket by market_id."""
        response = self.client.get(self._build_url(f"/markets/{market_id}"))
        response.raise_for_status()
        return GammaMarket(**response.json())

    def get_markets(
        self,
        limit: int | None = None,
        offset: int | None = None,
        order: str | None = None,
        ascending: bool = True,
        archived: bool | None = None,
        active: bool | None = None,
        closed: bool | None = None,
        slugs: list[str] | None = None,
        market_ids: list[int] | None = None,
        token_ids: list[str] | None = None,
        condition_ids: list[str] | None = None,
        tag_id: int | None = None,
        related_tags: bool | None = False,
        liquidity_num_min: float | None = None,
        liquidity_num_max: float | None = None,
        volume_num_min: float | None = None,
        volume_num_max: float | None = None,
        start_date_min: datetime | None = None,
        start_date_max: datetime | None = None,
        end_date_min: datetime | None = None,
        end_date_max: datetime | None = None,
    ) -> list[GammaMarket]:
        params: dict[str, float | int | list[int] | str | list[str] | bool] = {}
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

    def get_market_by_id(
        self, market_id: str, include_tag: Optional[bool] = None
    ) -> GammaMarket:
        params = {}
        if include_tag:
            params["include_tag"] = include_tag
        response = self.client.get(
            self._build_url(f"/markets/{market_id}"), params=params
        )
        response.raise_for_status()
        return GammaMarket(**response.json())

    def get_market_tags(self, market_id: str) -> list[Tag]:
        response = self.client.get(self._build_url(f"/markets/{market_id}/tags"))
        response.raise_for_status()
        return [Tag(**tag) for tag in response.json()]

    def get_market_by_slug(
        self, slug: str, include_tag: Optional[bool] = None
    ) -> GammaMarket:
        params = {}
        if include_tag:
            params["include_tag"] = include_tag
        response = self.client.get(
            self._build_url(f"/markets/slug/{slug}"), params=params
        )
        response.raise_for_status()
        return GammaMarket(**response.json())

    def get_events(
        self,
        limit: int = 500,
        offset: int = 0,
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
        params: dict[str, int | str | list[str] | float] = {
            "limit": limit,
            "offset": offset,
        }
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

    def get_event_by_id(
        self,
        event_id: int,
        include_chat: Optional[bool] = None,
        include_template: Optional[bool] = None,
    ) -> Event:
        params = {}
        if include_chat:
            params["include_chat"] = include_chat
        if include_template:
            params["include_template"] = include_template
        response = self.client.get(
            self._build_url(f"/events/{event_id}"), params=params
        )
        response.raise_for_status()
        return Event(**response.json())

    def get_event_by_slug(
        self,
        slug: str,
        include_chat: Optional[bool] = None,
        include_template: Optional[bool] = None,
    ) -> Event:
        params = {}
        if include_chat:
            params["include_chat"] = include_chat
        if include_template:
            params["include_template"] = include_template
        response = self.client.get(
            self._build_url(f"/events/slug/{slug}"), params=params
        )
        response.raise_for_status()
        return Event(**response.json())

    def get_event_tags(self, event_id: int) -> list[Tag]:
        response = self.client.get(self._build_url(f"/events/{event_id}/tags"))
        response.raise_for_status()
        return [Tag(**tag) for tag in response.json()]

    def get_teams(
        self,
        limit: int = 500,
        offset: int = 0,
        order: Optional[
            Literal[
                "id",
                "name",
                "league",
                "record",
                "logo",
                "abbreviation",
                "alias",
                "createdAt",
                "updatedAt",
            ]
        ] = None,
        ascending: bool = True,
        league: Optional[str] = None,
        name: Optional[str] = None,
        abbreviation: Optional[str] = None,
    ) -> list[Team]:
        params: dict[str, int | str] = {
            "limit": limit,
            "offset": offset,
        }
        if order:
            params["order"] = order
            params["ascending"] = str(ascending).lower()
        if league:
            params["league"] = league.lower()
        if name:
            params["name"] = name
        if abbreviation:
            params["abbreviation"] = abbreviation.lower()
        response = self.client.get(self._build_url("/teams"), params=params)
        response.raise_for_status()
        return [Team(**team) for team in response.json()]

    def get_all_teams(
        self,
        order: Optional[
            Literal[
                "id",
                "name",
                "league",
                "record",
                "logo",
                "abbreviation",
                "alias",
                "createdAt",
                "updatedAt",
            ]
        ] = None,
        ascending: bool = True,
        league: Optional[str] = None,
        name: Optional[str] = None,
        abbreviation: Optional[str] = None,
    ) -> list[Team]:
        offset = 0
        teams = []

        while True:
            part = self.get_teams(
                offset=offset,
                order=order,
                ascending=ascending,
                league=league,
                name=name,
                abbreviation=abbreviation,
            )
            teams.extend(part)

            if len(part) < 500:
                break

            offset += 500

        return teams

    def get_sports_metadata(
        self,
    ) -> list[Sport]:
        response = self.client.get(self._build_url("/sports"))
        response.raise_for_status()
        return [Sport(**sport) for sport in response.json()]

    def get_tags(
        self,
        limit: int = 300,
        offset: int = 0,
        order: Optional[
            Literal[
                "id",
                "label",
                "slug",
                "forceShow",
                "forceHide",
                "isCarousel",
                "createdAt",
                "updatedAt",
                "createdBy",
                "updatedBy",
            ]
        ] = None,
        ascending: bool = True,
        include_templates: Optional[bool] = None,
        is_carousel: Optional[bool] = None,
    ) -> list[Tag]:
        params: dict[str, int | str] = {
            "limit": limit,
            "offset": offset,
        }
        if order:
            params["order"] = order
            params["ascending"] = str(ascending).lower()
        if include_templates is not None:
            params["include_templates"] = str(include_templates).lower()
        if is_carousel is not None:
            params["is_carousel"] = str(is_carousel).lower()
        response = self.client.get(self._build_url("/tags"), params=params)
        response.raise_for_status()
        return [Tag(**tag) for tag in response.json()]

    def get_all_tags(
        self,
        order: Optional[
            Literal[
                "id",
                "label",
                "slug",
                "forceShow",
                "forceHide",
                "isCarousel",
                "createdAt",
                "updatedAt",
                "createdBy",
                "updatedBy",
            ]
        ] = None,
        ascending: bool = True,
        include_templates: Optional[bool] = None,
        is_carousel: Optional[bool] = None,
    ) -> list[Tag]:
        offset = 0
        tags = []

        while True:
            part = self.get_tags(
                offset=offset,
                order=order,
                ascending=ascending,
                include_templates=include_templates,
                is_carousel=is_carousel,
            )
            tags.extend(part)

            if len(part) < 300:
                break

            offset += 300

        return tags

    def get_tag(self, tag_id: str, include_template: Optional[bool] = None) -> Tag:
        params = {}
        if include_template is not None:
            params = {"include_template": str(include_template).lower()}
        response = self.client.get(self._build_url(f"/tags/{tag_id}"), params=params)
        response.raise_for_status()
        return Tag(**response.json())

    def get_related_tag_ids_by_tag_id(
        self,
        tag_id: int,
        omit_empty: Optional[bool] = None,
        status: Optional[Literal["active", "closed", "all"]] = None,
    ) -> list[TagRelation]:
        params = {}
        if omit_empty is not None:
            params["omit_empty"] = str(omit_empty).lower()
        if status:
            params["status"] = status
        response = self.client.get(
            self._build_url(f"/tags/{tag_id}/related-tags"), params=params
        )
        response.raise_for_status()
        return [TagRelation(**tag) for tag in response.json()]

    def get_related_tag_ids_by_slug(
        self,
        slug: str,
        omit_empty: Optional[bool] = None,
        status: Optional[Literal["active", "closed", "all"]] = None,
    ) -> list[TagRelation]:
        params = {}
        if omit_empty is not None:
            params["omit_empty"] = str(omit_empty).lower()
        if status:
            params["status"] = status
        response = self.client.get(
            self._build_url(f"/tags/slug/{slug}/related-tags"), params=params
        )
        response.raise_for_status()
        return [TagRelation(**tag) for tag in response.json()]

    def get_related_tags_by_tag_id(
        self,
        tag_id: int,
        omit_empty: Optional[bool] = None,
        status: Optional[Literal["active", "closed", "all"]] = None,
    ) -> list[Tag]:
        params = {}
        if omit_empty is not None:
            params["omit_empty"] = str(omit_empty).lower()
        if status:
            params["status"] = status
        response = self.client.get(
            self._build_url(f"/tags/{tag_id}/related-tags/tags"), params=params
        )
        response.raise_for_status()
        return [Tag(**tag) for tag in response.json()]

    def get_related_tags_by_slug(
        self,
        slug: str,
        omit_empty: Optional[bool] = None,
        status: Optional[Literal["active", "closed", "all"]] = None,
    ) -> list[Tag]:
        params = {}
        if omit_empty is not None:
            params["omit_empty"] = str(omit_empty).lower()
        if status:
            params["status"] = status
        response = self.client.get(
            self._build_url(f"/tags/slug/{slug}/related-tags/tags"), params=params
        )
        response.raise_for_status()
        return [Tag(**tag) for tag in response.json()]

    def get_series(
        self,
        limit: int = 300,
        offset: int = 0,
        order: Optional[str] = None,
        ascending: bool = True,
        slug: Optional[str] = None,
        closed: Optional[bool] = None,
        include_chat: Optional[bool] = None,
        recurrence: Optional[
            Literal[
                "hourly", "daily", "weekly", "monthly", "annual"
            ]  # results also contain "15m" but the server returns a 422 Unprocessable Content
        ] = None,
    ) -> list[Series]:
        params: dict[str, str | int | list[int]] = {
            "limit": limit,
            "offset": offset,
        }
        if order:
            params["order"] = order
            params["ascending"] = str(ascending).lower()
        if slug:
            params["slug"] = slug
        if closed is not None:
            params["closed"] = str(closed).lower()
        if include_chat is not None:
            params["include_chat"] = str(include_chat).lower()
        if recurrence is not None:
            params["recurrence"] = str(recurrence).lower()

        response = self.client.get(self._build_url("/series"), params=params)
        response.raise_for_status()
        return [Series(**series) for series in response.json()]

    def get_all_series(
        self,
        order: Optional[str] = None,
        ascending: bool = True,
        slug: Optional[str] = None,
        closed: Optional[bool] = None,
        include_chat: Optional[bool] = None,
        recurrence: Optional[
            Literal["hourly", "daily", "weekly", "monthly", "annual"]
        ] = None,
    ) -> list[Series]:
        offset = 0
        series = []

        while True:
            part = self.get_series(
                offset=offset,
                order=order,
                ascending=ascending,
                slug=slug,
                closed=closed,
                include_chat=include_chat,
                recurrence=recurrence,
            )
            series.extend(part)

            if len(part) < 300:
                break

            offset += 300
        return series

    def get_series_by_id(self, series_id: str) -> Series:
        response = self.client.get(self._build_url(f"/series/{series_id}"))
        response.raise_for_status()
        return Series(**response.json())

    def get_comments(
        self,
        parent_entity_type: Literal["Event", "Series", "market"],
        parent_entity_id: int,
        limit=500,
        offset=0,
        order: Optional[str] = None,
        ascending: bool = True,
        get_positions: Optional[bool] = None,
        holders_only: Optional[bool] = None,
    ) -> list[Comment]:
        """Warning, the server doesn't give back the right amount of comments you asked for."""
        params: dict[str, str | int] = {
            "parent_entity_type": parent_entity_type,
            "parent_entity_id": parent_entity_id,
            "limit": limit,
            "offset": offset,
        }
        if order:
            params["order"] = order
            params["ascending"] = str(ascending).lower()
        if get_positions is not None:
            params["get_positions"] = str(get_positions).lower()
        if holders_only is not None:
            params["holders_only"] = str(holders_only).lower()
        response = self.client.get(self._build_url("/comments"), params=params)
        response.raise_for_status()
        return [Comment(**comment) for comment in response.json()]

    def get_comments_by_id(
        self, comment_id: str, get_positions: Optional[bool] = None
    ) -> list[Comment]:
        """Returns all comments that belong to the comment's thread."""
        params = {}
        if get_positions is not None:
            params["get_positions"] = str(get_positions).lower()
        response = self.client.get(
            self._build_url(f"/comments/{comment_id}"), params=params
        )
        response.raise_for_status()
        return [Comment(**comment) for comment in response.json()]

    def get_comments_by_user_address(
        self,
        user_address: EthAddress,  # warning, this is the base address, not the proxy address
        limit=500,
        offset=0,
        order: Optional[str] = None,
        ascending: bool = True,
    ) -> list[Comment]:
        params: dict[str, str | int] = {
            "limit": limit,
            "offset": offset,
        }
        if order:
            params["order"] = order
            params["ascending"] = str(ascending).lower()
        response = self.client.get(
            self._build_url(f"/comments/user_address/{user_address}"), params=params
        )
        response.raise_for_status()
        return [Comment(**comment) for comment in response.json()]

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
