from datetime import datetime
from typing import Optional, Union
from urllib.parse import urljoin
import json


import httpx

from ..types.gamma_types import Event, GammaMarket, QueryEvent


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
            ids: Optional[list[int]] = None,
            slugs: Optional[list[str]] = None,
            archived: Optional[bool] = None,
            active: Optional[bool] = None,
            closed: Optional[bool] = None,
            token_ids: Optional[list[str]] = None,
            condition_ids: Optional[list[str]] = None,
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
    ) -> list[GammaMarket]:
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
        """
        Get a GammaMarket by market_id
        """
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

    def search_events(self, query: str) -> list[QueryEvent]:
        """
        Search for events by query
        """

        # TODO take pagination into account and maybe add other filters
        # https://polymarket.com/api/events/search?_c=all&_q=trump&_s=volume:desc&_p=1

        params = {"q": query}
        response = self.client.get("https://polymarket.com/api/events/global", params=params)
        response.raise_for_status()
        return [QueryEvent(**event) for event in response.json()["events"]]

    def grok_market_summary(self, condition_id: str):
        market = self.get_markets(condition_ids=[condition_id])[0]

        params = {
            "marketName": market.group_item_title,
            "eventTitle": market.question,
            "odds": market.outcome_prices[0],
            "marketDescription": market.description,
            "isNegRisk": market.neg_risk
        }

        with self.client.stream(method="GET", url="https://polymarket.com/api/grok/market-explanation", params=params) as stream:
            messages = []
            citations = []
            for line in stream.iter_lines():
                if line:
                    line_str = line
                    if line_str.startswith('data: '):
                        json_part = line_str[len('data: '):]
                        try:
                            data = json.loads(json_part)
                            # Extract content if present
                            content = data.get('choices', [{}])[0].get('delta', {}).get('content', '')
                            if content:
                                messages.append(content)
                                print(content, end='')  # Stream content
                            # Extract citations if present
                            if 'citations' in data:
                                citations.extend(data['citations'])
                        except json.JSONDecodeError:
                            pass

        # After streaming, print citations if any
        if citations:
            print("\n\nCitations:")
            for cite in citations:
                print(f"- {cite}")

    def grok_event_summary(self, event_slug: str):
        params = {
            "prompt": event_slug
        }

        with self.client.stream(method="GET", url="https://polymarket.com/api/grok/event-summary", params=params) as stream:
            messages = []
            citations = []
            for line in stream.iter_lines():
                if line:
                    line_str = line
                    if line_str.startswith('data: '):
                        json_part = line_str[len('data: '):]
                        try:
                            data = json.loads(json_part)
                            # Extract content if present
                            content = data.get('choices', [{}])[0].get('delta', {}).get('content', '')
                            if content:
                                messages.append(content)
                                print(content, end='')  # Stream content
                            # Extract citations if present
                            if 'citations' in data:
                                citations.extend(data['citations'])
                        except json.JSONDecodeError:
                            pass

        # After streaming, print citations if any
        if citations:
            print("\n\nCitations:")
            for cite in citations:
                print(f"- {cite}")
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()
