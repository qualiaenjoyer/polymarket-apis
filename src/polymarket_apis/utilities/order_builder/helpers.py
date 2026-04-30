import hashlib
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Optional

from ...types.clob_types import OrderBookSummary, OrderType, TickSize
from .model import SignedOrder


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


def adjust_market_buy_amount(
    amount: float,
    user_usdc_balance: float,
    price: float,
    fee_rate: float,
    fee_exponent: float,
) -> float:
    """Return a market-buy amount that fits the user's pUSD balance after fees."""
    d_amount = Decimal(str(amount))
    d_price = Decimal(str(price))
    d_balance = Decimal(str(user_usdc_balance))
    d_fee_rate = Decimal(str(fee_rate))
    d_fee_exponent = Decimal(str(fee_exponent))

    base = float(d_price * (Decimal(1) - d_price))
    d_price_fee_rate = d_fee_rate * Decimal(str(base ** float(d_fee_exponent)))
    platform_fee = d_amount / d_price * d_price_fee_rate
    total_cost = d_amount + platform_fee

    if d_balance <= total_cost:
        divisor = Decimal(1) + d_price_fee_rate / d_price
        return float(d_balance / divisor)
    return amount


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


def order_to_json(
    order: SignedOrder,
    owner: str,
    order_type: OrderType,
    post_only: Optional[bool] = False,
    defer_exec: Optional[bool] = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "order": order.dict(),
        "owner": owner,
        "orderType": order_type.value,
    }
    if defer_exec is not None:
        payload["deferExec"] = defer_exec
    if post_only is not None:
        payload["postOnly"] = post_only
    return payload


def is_tick_size_smaller(a: TickSize, b: TickSize) -> bool:
    return float(a) < float(b)


def price_valid(price: float, tick_size: TickSize) -> bool:
    return float(tick_size) <= price <= 1 - float(tick_size)
