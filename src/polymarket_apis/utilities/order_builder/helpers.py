from math import floor, ceil
from decimal import Decimal

import hashlib
from ...types.clob_types import OrderBookSummary, TickSize


def round_down(x: float, sig_digits: int) -> float:
    return floor(x * (10**sig_digits)) / (10**sig_digits)


def round_normal(x: float, sig_digits: int) -> float:
    return round(x * (10**sig_digits)) / (10**sig_digits)


def round_up(x: float, sig_digits: int) -> float:
    return ceil(x * (10**sig_digits)) / (10**sig_digits)


def to_token_decimals(x: float) -> int:
    f = (10**6) * x
    if decimal_places(f) > 0:
        f = round_normal(f, 0)
    return int(f)


def decimal_places(x: float) -> int:
    return abs(Decimal(x.__str__()).as_tuple().exponent)


def generate_orderbook_summary_hash(orderbook: OrderBookSummary) -> str:
    """Compute hash while forcing empty string for hash field"""
    server_hash = orderbook.hash
    orderbook.hash = ""
    computed_hash = hashlib.sha1(
        str(orderbook.model_dump_json(by_alias=True)).encode("utf-8")
    ).hexdigest()
    orderbook.hash = server_hash
    return computed_hash


def order_to_json(order, owner, order_type) -> dict:
    return {"order": order.dict(), "owner": owner, "orderType": order_type.value}


def is_tick_size_smaller(a: TickSize, b: TickSize) -> bool:
    return float(a) < float(b)


def price_valid(price: float, tick_size: TickSize) -> bool:
    return float(tick_size) <= price <= 1 - float(tick_size)
