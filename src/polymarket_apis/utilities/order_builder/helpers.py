import hashlib
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from ...types.clob_types import OrderBookSummary, TickSize


def round_down(x: float, sig_digits: int) -> float:
    exp = Decimal(1).scaleb(-sig_digits)
    return float(Decimal(str(x)).quantize(exp=exp, rounding=ROUND_FLOOR))


def round_normal(x: float, sig_digits: int) -> float:
    exp = Decimal(1).scaleb(-sig_digits)
    return float(Decimal(str(x)).quantize(exp=exp, rounding=ROUND_HALF_UP))


def round_up(x: float, sig_digits: int) -> float:
    exp = Decimal(1).scaleb(-sig_digits)
    return float(Decimal(str(x)).quantize(exp=exp, rounding=ROUND_CEILING))


def to_token_decimals(x: float) -> int:
    exp = Decimal(1)
    return int(
        Decimal(str(x)) * Decimal(10**6).quantize(exp=exp, rounding=ROUND_HALF_UP),
    )


def decimal_places(x: float) -> int:
    """
    Returns the number of decimal places in a numeric value.

    Assumes x is always a finite, non-special value (not NaN or Infinity).
    """
    exponent = Decimal(str(x)).as_tuple().exponent
    if not isinstance(exponent, int):
        msg = "Input must be a finite float."
        raise TypeError(msg)
    return max(0, -exponent)



def generate_orderbook_summary_hash(orderbook: OrderBookSummary) -> str:
    """Compute hash while forcing empty string for hash field."""
    server_hash = orderbook.hash
    orderbook.hash = ""
    computed_hash = hashlib.sha1(
        str(orderbook.model_dump_json(by_alias=True)).encode("utf-8"),
    ).hexdigest()
    orderbook.hash = server_hash
    return computed_hash


def order_to_json(order, owner, order_type) -> dict:
    return {"order": order.dict(), "owner": owner, "orderType": order_type.value}


def is_tick_size_smaller(a: TickSize, b: TickSize) -> bool:
    return float(a) < float(b)


def price_valid(price: float, tick_size: TickSize) -> bool:
    return float(tick_size) <= price <= 1 - float(tick_size)
