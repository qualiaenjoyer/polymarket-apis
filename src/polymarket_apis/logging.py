"""
Opt-in logging helpers for ``polymarket_apis``.

SDK modules always emit standard-library ``logging`` records with structured
``extra`` fields. Importing this module has no side effects; call
``configure_logging`` only if you want the SDK's opinionated JSON/text setup.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
from queue import Queue
from typing import IO, Any, Literal, Self

DEFAULT_LOG_FIELDS = (
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
_STANDARD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class DefaultFieldsFilter(logging.Filter):
    """Ensure common SDK fields exist for vanilla formatters."""

    def __init__(self, fields: Iterable[str] = DEFAULT_LOG_FIELDS) -> None:
        super().__init__()
        self.fields = tuple(fields)

    def filter(self, record: logging.LogRecord) -> bool:
        for field in self.fields:
            if not hasattr(record, field):
                setattr(record, field, None)
        return True


class JsonFormatter(logging.Formatter):
    """JSON-lines formatter for SDK log records."""

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
        }

        payload.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in _STANDARD_ATTRS and value is not None
            }
        )

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(payload, separators=(",", ":"), default=str)


class TextFormatter(logging.Formatter):
    """Readable text formatter with the most useful trading context."""

    def __init__(self) -> None:
        super().__init__(
            "%(asctime)s %(levelname)s %(name)s "
            "event=%(event)s trace=%(trace_id)s order=%(order_id)s "
            "tx=%(tx_hash)s latency_ms=%(latency_ms)s msg=%(message)s"
        )


@dataclass
class LoggingHandle:
    """Handle returned by queued logging setup so callers can flush cleanly."""

    listener: QueueListener | None = None

    def stop(self) -> None:
        if self.listener is not None:
            self.listener.stop()
            self.listener = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()


def _build_output_handler(
    output: str | Path,
    *,
    max_bytes: int,
    backup_count: int,
) -> logging.Handler:
    if output == "stdout":
        return logging.StreamHandler(sys.stdout)
    if output == "stderr":
        return logging.StreamHandler(sys.stderr)

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    return RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )


def configure_logging(
    *,
    level: str | int = "INFO",
    format: Literal["json", "text"] = "json",
    output: str | Path | IO[str] = "stdout",
    queue: bool = True,
    logger_name: str = "polymarket_apis",
    propagate: bool = False,
    max_bytes: int = 100 * 1024 * 1024,
    backup_count: int = 5,
) -> LoggingHandle:
    """
    Configure opinionated SDK logging without touching the root logger.

    Users with existing logging should skip this function and attach their own
    handlers to ``logging.getLogger("polymarket_apis")`` or pass a per-client
    logger.
    """
    level_int = (
        level if isinstance(level, int) else getattr(logging, level.upper(), logging.INFO)
    )
    formatter: logging.Formatter = JsonFormatter() if format == "json" else TextFormatter()


    sink: logging.Handler
    if isinstance(output, (str, Path)):
        sink = _build_output_handler(
            output,
            max_bytes=max_bytes,
            backup_count=backup_count,
        )
    else:
        sink = logging.StreamHandler(output)

    sink.setLevel(level_int)
    sink.setFormatter(formatter)
    sink.addFilter(DefaultFieldsFilter())

    target = logging.getLogger(logger_name)
    target.handlers.clear()
    target.setLevel(level_int)
    target.propagate = propagate

    if queue:
        log_queue: Queue[logging.LogRecord] = Queue(-1)
        queue_handler = QueueHandler(log_queue)
        queue_handler.setLevel(level_int)
        queue_handler.addFilter(DefaultFieldsFilter())
        target.addHandler(queue_handler)
        listener = QueueListener(log_queue, sink, respect_handler_level=True)
        listener.start()
        return LoggingHandle(listener=listener)

    target.addHandler(sink)
    return LoggingHandle()


def configure_file_logging(
    path: str | Path,
    *,
    level: str | int = "INFO",
    format: Literal["json", "text"] = "json",
    queue: bool = True,
    logger_name: str = "polymarket_apis",
    max_bytes: int = 100 * 1024 * 1024,
    backup_count: int = 5,
) -> LoggingHandle:
    """Convenience wrapper for JSONL/text file logging."""
    return configure_logging(
        level=level,
        format=format,
        output=path,
        queue=queue,
        logger_name=logger_name,
        max_bytes=max_bytes,
        backup_count=backup_count,
    )


def configure(
    level: str = "INFO",
    json_format: bool = True,
    logger_name: str = "polymarket_apis",
    output_stream: Any = sys.stdout,
) -> None:
    """Backward-compatible alias for the previous opt-in helper."""
    configure_logging(
        level=level,
        format="json" if json_format else "text",
        output=output_stream,
        queue=False,
        logger_name=logger_name,
    )
