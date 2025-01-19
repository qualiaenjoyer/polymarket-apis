from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urljoin

import httpx

from ..types.clob_types import (
    ApiCreds,
    RequestArgs,
)
from ..types.common import EthAddress
from ..utilities.constants import AMOY, POLYGON
from ..utilities.endpoints import (
    CREATE_API_KEY,
    DELETE_API_KEY,
    DERIVE_API_KEY,
    GET_API_KEYS,
    TIME,
)
from ..utilities.headers import create_level_1_headers, create_level_2_headers
from ..utilities.order_builder.builder import OrderBuilder
from ..utilities.signing.signer import Signer


class PolymarketClobClient:
    def __init__(
        self,
        private_key: str,
        proxy_address: EthAddress,
        creds: ApiCreds = None,
        chain_id: Literal[POLYGON, AMOY] = POLYGON,
    ):
        self.client = httpx.Client(http2=True, timeout=30.0)
        self.base_url: str = "https://clob.polymarket.com"
        self.signature_type = 2
        self.signer = Signer(private_key=private_key, chain_id=chain_id)
        self.builder = OrderBuilder(
            signer=self.signer, sig_type=self.signature_type, funder=proxy_address
        )
        self.creds = creds if creds else self.derive_api_key()

    def _build_url(self, endpoint: str) -> str:
        return urljoin(self.base_url, endpoint)

    def derive_api_key(self, nonce: int = None) -> ApiCreds:
        headers = create_level_1_headers(self.signer, nonce)
        response = self.client.get(self._build_url(DERIVE_API_KEY), headers=headers)
        return ApiCreds(**response.json())

    def create_api_creds(self, nonce: int = None) -> ApiCreds:
        headers = create_level_1_headers(self.signer, nonce)
        response = self.client.post(self._build_url(CREATE_API_KEY), headers=headers)
        return ApiCreds(**response.json())

    def create_or_derive_api_creds(self, nonce: int = None) -> ApiCreds:
        try:
            return self.create_api_creds(nonce)
        except:
            return self.derive_api_key(nonce)

    def set_api_creds(self, creds: ApiCreds):
        self.creds = creds

    def get_api_keys(self) -> ApiCreds:
        request_args = RequestArgs(method="GET", request_path=GET_API_KEYS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.client.get(self._build_url(GET_API_KEYS), headers=headers)
        return response.json()

    def delete_api_keys(self) -> ApiCreds:
        request_args = RequestArgs(method="DELETE", request_path=DELETE_API_KEY)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.client.delete(self._build_url(DELETE_API_KEY), headers=headers)
        return response.json()

    def get_utc_time(self) -> datetime:
        # parse server timestamp into utc datetime
        response = self.client.get(self._build_url(TIME))
        response.raise_for_status()
        return datetime.fromtimestamp(response.json(), tz=timezone.utc)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()
