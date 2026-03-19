"""Testing helpers for live contract checks and other SDK test utilities."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .contract_assertions import assert_api_contract, fail_contract, fetch_json

__all__ = ["assert_api_contract", "fail_contract", "fetch_json"]

_EXPORT_MAP = {
    "assert_api_contract": ".contract_assertions",
    "fail_contract": ".contract_assertions",
    "fetch_json": ".contract_assertions",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MAP.get(name)
    if module_name is None:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)

    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
