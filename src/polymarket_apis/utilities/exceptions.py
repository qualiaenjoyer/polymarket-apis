from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from httpx import Response


class PolymarketError(Exception):
    """Base for all SDK errors."""



# --- HTTP Errors ---
class PolymarketHTTPError(PolymarketError):
    """Any HTTP-level error from a Polymarket API call."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        response_body: dict[str, Any] | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body or {}
        self.retry_after = retry_after

    def is_retryable(self) -> bool:
        """Return True if this error is safe to retry."""
        return self.status_code in RETRYABLE_CODES


class BadRequestError(PolymarketHTTPError):
    """400 — the request was malformed."""


class AuthenticationError(PolymarketHTTPError):
    """401 — invalid or missing credentials."""


class PermissionError(PolymarketHTTPError):
    """403 — valid credentials but insufficient permissions."""


class NotFoundError(PolymarketHTTPError):
    """404 — the requested resource does not exist."""


class UnprocessableEntityError(PolymarketHTTPError):
    """422 — semantic errors in the request body."""


class RateLimitError(PolymarketHTTPError):
    """429 — too many requests. Check ``retry_after``."""


class ServerError(PolymarketHTTPError):
    """5xx — server-side error, safe to retry with backoff."""


# --- Domain / Trading Errors ---
class PolymarketDomainError(PolymarketError):
    """Business-logic error raised before an HTTP call is made."""



class InvalidPriceError(PolymarketDomainError):
    """Order price violates tick-size or market bounds."""


class InvalidTickSizeError(PolymarketDomainError):
    """Tick size is smaller than the market minimum."""


class InvalidFeeRateError(PolymarketDomainError):
    """Fee rate provided by the user does not match the market fee rate."""


class LiquidityError(PolymarketDomainError):
    """Insufficient liquidity to fill the requested order."""


class MissingOrderbookError(PolymarketDomainError):
    """Orderbook is empty or unavailable for the token."""


# --- Order Lifecycle Errors ---
class PolymarketOrderError(PolymarketDomainError):
    """Order post/cancel lifecycle error."""

    def __init__(self, message: str, *, order_id: str | None = None) -> None:
        super().__init__(message)
        self.order_id = order_id


class OrderPlacementError(PolymarketOrderError):
    """The server rejected an order placement request."""

    def __init__(
        self,
        message: str,
        *,
        order_id: str | None = None,
        status_code: int | None = None,
        response_body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, order_id=order_id)
        self.status_code = status_code
        self.response_body = response_body or {}


class OrderCancellationError(PolymarketOrderError):
    """The server rejected an order cancellation request."""


class OrderValidationError(PolymarketOrderError):
    """Order failed local validation before being sent to the server."""


# --- Web3 Errors ---
class PolymarketWeb3Error(PolymarketDomainError):
    """Blockchain-level error."""

    def __init__(
        self,
        message: str,
        *,
        tx_hash: str | None = None,
        nonce: int | None = None,
    ) -> None:
        super().__init__(message)
        self.tx_hash = tx_hash
        self.nonce = nonce


class TransactionFailedError(PolymarketWeb3Error):
    """Transaction was mined but reverted on-chain (status == 0)."""


class TransactionTimeoutError(PolymarketWeb3Error):
    """Transaction was submitted but not confirmed within the timeout window."""


class NonceError(PolymarketWeb3Error):
    """Nonce mismatch or collision detected."""


# --- Legacy / Keep for backward-compat ---
class SafeAlreadyDeployedError(PolymarketError):
    """Raised when attempting to deploy a Safe that has already been deployed."""


class BuilderRateLimitError(PolymarketError):
    """Shared builder credentials have hit their rate limit."""


# --- Constants ---
RETRYABLE_CODES = {429, 500, 502, 503, 504}


# --- Factory ---
def make_status_error(
    response: Response, body: dict[str, Any] | None = None
) -> PolymarketHTTPError:
    """
    Create a typed HTTP error from an ``httpx.Response``.

    Example::

        try:
            response = client.get(...)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.json() if exc.response.headers.get("content-type", "").startswith("application/json") else None
            raise make_status_error(exc.response, body) from exc
    """
    status = response.status_code
    retry_after = None
    if status == 429:
        retry_after = float(response.headers.get("Retry-After", 0.0)) or None

    body = body or {}
    message = body.get("error") or body.get("message") or f"HTTP {status}"
    cls = {
        400: BadRequestError,
        401: AuthenticationError,
        403: PermissionError,
        404: NotFoundError,
        422: UnprocessableEntityError,
        429: RateLimitError,
    }.get(status, ServerError if status >= 500 else PolymarketHTTPError)

    return cls(
        message,
        status_code=status,
        response_body=body,
        retry_after=retry_after,
    )
