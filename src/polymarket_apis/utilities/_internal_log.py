"""
Internal logging utilities for polymarket_apis.

SDK code uses these; users configure them via stdlib logging or opt-in
`polymarket_apis.logging.configure()`.

No import-time side effects. No root-logger configuration.
"""

from __future__ import annotations

import contextvars
import logging
import time
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Self

# Context propagation for correlation IDs without forcing any logging backend.
_TRACE_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "polymarket_trace_id", default=None
)
_OPERATION_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "polymarket_operation_id", default=None
)
_STRATEGY_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "polymarket_strategy_id", default=None
)

_REDACTED = "[REDACTED]"
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "passphrase",
    "private_key",
    "secret",
    "signature",
)
_LOG_RECORD_RESERVED = set(logging.makeLogRecord({}).__dict__)
_DEFAULT_EXTRA_FIELDS: tuple[str, ...] = (
    "event",
    "trace_id",
    "operation_id",
    "strategy_id",
    "operation",
    "web3_action",
    "phase",
    "success",
    "latency_ms",
    "order_id",
    "order_ids",
    "client_order_id",
    "token_id",
    "side",
    "price",
    "price_display",
    "size",
    "size_display",
    "notional",
    "notional_display",
    "maker_amount",
    "taker_amount",
    "order_type",
    "order_source",
    "requested_amount",
    "requested_amount_display",
    "post_only",
    "defer_exec",
    "idempotency_key",
    "status",
    "status_code",
    "error_type",
    "error_detail",
    "cancel_scope",
    "cancelled_count",
    "cancelled_order_ids",
    "not_cancelled",
    "requested_order_ids",
    "cancel_filter",
    "tx_hash",
    "transaction_id",
    "nonce",
    "chain_id",
    "wallet_address",
    "wallet_type",
    "condition_id",
    "question_ids",
    "amount",
    "atomic_amount",
    "neg_risk",
    "gas_price",
    "gas_used",
    "gas_cost_pol",
    "block_number",
    "metadata",
    "expiration",
    "expiration_iso",
)


def _is_sensitive_key(key: str) -> bool:
    key_lower = key.lower()
    if key_lower == "signature_type":
        return False
    return any(part in key_lower for part in _SENSITIVE_KEY_PARTS)


def get_trace_id() -> str | None:
    """Get the current trace ID, if any."""
    return _TRACE_ID.get()


def set_trace_id(tid: str | None) -> None:
    """Set the current trace ID for this context (thread/async-local)."""
    _TRACE_ID.set(tid)


def get_operation_id() -> str | None:
    """Get the current operation ID, if any."""
    return _OPERATION_ID.get()


def set_operation_id(operation_id: str | None) -> None:
    """Set the current operation ID for this context."""
    _OPERATION_ID.set(operation_id)


def get_strategy_id() -> str | None:
    """Get the current strategy ID, if any."""
    return _STRATEGY_ID.get()


def set_strategy_id(strategy_id: str | None) -> None:
    """Set the current strategy ID for this context."""
    _STRATEGY_ID.set(strategy_id)


def with_trace_id(tid: str | None = None) -> str:
    """
    Set or generate a trace ID for the current context. Returns the ID.

    Example:
        >>> from polymarket_apis.utilities._internal_log import with_trace_id
        >>> trace = with_trace_id()   # auto-generated nanosecond ID
        >>> trace = with_trace_id("my-strategy-42")

    """
    new_id = tid or f"poly_{time.time_ns()}"
    set_trace_id(new_id)
    return new_id


def current_or_new_trace_id(tid: str | None = None) -> str:
    """Return the current trace ID, or set/generate one if absent."""
    return tid or get_trace_id() or with_trace_id()


def ensure_trace_id(tid: str | None = None) -> tuple[str, contextvars.Token[str | None] | None]:
    """Return a trace ID and token if this call created a temporary trace."""
    if tid is not None:
        return tid, None
    existing = get_trace_id()
    if existing is not None:
        return existing, None
    new_id = f"poly_{time.time_ns()}"
    return new_id, _TRACE_ID.set(new_id)


def reset_trace_id(token: contextvars.Token[str | None] | None) -> None:
    """Reset a temporary trace created by ``ensure_trace_id``."""
    if token is not None:
        _TRACE_ID.reset(token)


def clear_trace_id() -> None:
    """Clear the current trace ID."""
    _TRACE_ID.set(None)


class PolymarketContext:
    """Temporarily bind trading context fields to SDK log records."""

    def __init__(
        self,
        *,
        trace_id: str | None = None,
        operation_id: str | None = None,
        strategy_id: str | None = None,
    ) -> None:
        self.trace_id = trace_id
        self.operation_id = operation_id
        self.strategy_id = strategy_id
        self._trace_token: contextvars.Token[str | None] | None = None
        self._operation_token: contextvars.Token[str | None] | None = None
        self._strategy_token: contextvars.Token[str | None] | None = None

    def __enter__(self) -> Self:
        if self.trace_id is not None:
            self._trace_token = _TRACE_ID.set(self.trace_id)
        if self.operation_id is not None:
            self._operation_token = _OPERATION_ID.set(self.operation_id)
        if self.strategy_id is not None:
            self._strategy_token = _STRATEGY_ID.set(self.strategy_id)
        return self

    def __exit__(self, *args: object) -> None:
        if self._trace_token is not None:
            _TRACE_ID.reset(self._trace_token)
        if self._operation_token is not None:
            _OPERATION_ID.reset(self._operation_token)
        if self._strategy_token is not None:
            _STRATEGY_ID.reset(self._strategy_token)


def polymarket_context(
    *,
    trace_id: str | None = None,
    operation_id: str | None = None,
    strategy_id: str | None = None,
) -> PolymarketContext:
    """Return a context manager that binds trading context to SDK logs."""
    return PolymarketContext(
        trace_id=trace_id,
        operation_id=operation_id,
        strategy_id=strategy_id,
    )


def get_logger(name: str) -> logging.Logger:
    """
    Return a namespaced logger.

    Users control verbosity via ``logging.getLogger("polymarket_apis")``.
    """
    return logging.getLogger(name)


def _safe_value(key: str, value: Any) -> Any:
    if _is_sensitive_key(key):
        return _REDACTED
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _safe_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_safe_value(key, item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return _safe_value(key, asdict(value))
    if hasattr(value, "model_dump"):
        return _safe_value(
            key,
            value.model_dump(mode="json", by_alias=False, exclude_none=True),
        )
    return str(value)


def log_extra(**kwargs: Any) -> dict[str, Any]:
    """
    Build extra dict for stdlib ``logging.Logger.*(..., extra=...)``.

    Automatically injects the current trace ID if one exists.

    Example::

        logger.info(
            "Order placed",
            extra=log_extra(order_id=oid, latency_ms=42.0),
        )
    """
    extra: dict[str, Any] = dict.fromkeys(_DEFAULT_EXTRA_FIELDS, "")
    tid = kwargs.pop("trace_id", None) or get_trace_id()
    if tid:
        extra["trace_id"] = tid
    operation_id = kwargs.pop("operation_id", None) or get_operation_id()
    if operation_id:
        extra["operation_id"] = operation_id
    strategy_id = kwargs.pop("strategy_id", None) or get_strategy_id()
    if strategy_id:
        extra["strategy_id"] = strategy_id
    for key, value in kwargs.items():
        extra_key = f"poly_{key}" if key in _LOG_RECORD_RESERVED else key
        extra[extra_key] = _safe_value(extra_key, value)
    return extra


def emit(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str,
    *args: Any,
    **fields: Any,
) -> None:
    """Emit a structured stdlib log record with a stable event name."""
    logger.log(level, message, *args, extra=log_extra(event=event, **fields))
