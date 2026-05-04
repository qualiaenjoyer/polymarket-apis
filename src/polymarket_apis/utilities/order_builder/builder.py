import time
from typing import Literal

from eth_typing import ChecksumAddress

from ...types.clob_types import (
    CreateOrderOptions,
    MarketOrderArgs,
    OrderArgs,
    OrderSummary,
    OrderType,
    RoundConfig,
    TickSize,
)
from ..config import get_contract_config
from ..constants import BUY, BYTES32_ZERO, SELL
from ..exceptions import LiquidityError
from ..signing.signer import Signer
from .helpers import (
    decimal_places,
    round_down,
    round_normal,
    round_up,
    to_token_decimals,
)
from .model import (
    BUY_SIDE,
    EOA,
    POLY_1271,
    SELL_SIDE,
    OrderData,
    SignedOrder,
)
from .model import (
    OrderBuilder as V2OrderBuilder,
)

ROUNDING_CONFIG: dict[TickSize, RoundConfig] = {
    "0.1": RoundConfig(price=1, size=2, amount=3),
    "0.01": RoundConfig(price=2, size=2, amount=4),
    "0.001": RoundConfig(price=3, size=2, amount=5),
    "0.0001": RoundConfig(price=4, size=2, amount=6),
}


class OrderBuilder:
    def __init__(
        self,
        signer: Signer,
        sig_type: int | None = None,
        funder: ChecksumAddress | None = None,
    ):
        self.signer = signer

        # Signature type used sign orders, defaults to EOA type
        self.sig_type = sig_type if sig_type is not None else EOA

        if self.sig_type == POLY_1271 and funder is None:
            msg = "signature type POLY_1271 requires a funder/deposit wallet address"
            raise ValueError(msg)

        # Address which holds funds to be used.
        # Used for Polymarket proxy wallets and other smart contract wallets
        # Defaults to the address of the signer
        self.funder = funder if funder is not None else self.signer.address()

    def _v2_order_signer(self) -> ChecksumAddress:
        if self.sig_type == POLY_1271:
            return self.funder
        return self.signer.address()

    def get_order_amounts(
        self,
        side: str,
        size: float,
        price: float,
        round_config: RoundConfig,
    ) -> tuple[Literal[0, 1], int, int]:
        raw_price = round_normal(price, round_config.price)

        if side == BUY:
            raw_taker_amt = round_down(size, round_config.size)

            raw_maker_amt = raw_taker_amt * raw_price
            if decimal_places(raw_maker_amt) > round_config.amount:
                raw_maker_amt = round_up(raw_maker_amt, round_config.amount + 4)
                if decimal_places(raw_maker_amt) > round_config.amount:
                    raw_maker_amt = round_down(raw_maker_amt, round_config.amount)

            maker_amount = to_token_decimals(raw_maker_amt)
            taker_amount = to_token_decimals(raw_taker_amt)

            return BUY_SIDE, maker_amount, taker_amount
        if side == SELL:
            raw_maker_amt = round_down(size, round_config.size)

            raw_taker_amt = raw_maker_amt * raw_price
            if decimal_places(raw_taker_amt) > round_config.amount:
                raw_taker_amt = round_up(raw_taker_amt, round_config.amount + 4)
                if decimal_places(raw_taker_amt) > round_config.amount:
                    raw_taker_amt = round_down(raw_taker_amt, round_config.amount)

            maker_amount = to_token_decimals(raw_maker_amt)
            taker_amount = to_token_decimals(raw_taker_amt)

            return SELL_SIDE, maker_amount, taker_amount
        msg = f"order_args.side must be '{BUY}' or '{SELL}'"
        raise ValueError(msg)

    def get_market_order_amounts(
        self,
        side: str,
        amount: float,
        price: float,
        round_config: RoundConfig,
    ) -> tuple[Literal[0, 1], int, int]:
        raw_price = round_down(price, round_config.price)

        if side == BUY:
            raw_maker_amt = round_down(amount, round_config.size)
            raw_taker_amt = raw_maker_amt / raw_price
            if decimal_places(raw_taker_amt) > round_config.amount:
                raw_taker_amt = round_up(raw_taker_amt, round_config.amount + 4)
                if decimal_places(raw_taker_amt) > round_config.amount:
                    raw_taker_amt = round_down(raw_taker_amt, round_config.amount)

            maker_amount = to_token_decimals(raw_maker_amt)
            taker_amount = to_token_decimals(raw_taker_amt)

            return BUY_SIDE, maker_amount, taker_amount

        if side == SELL:
            raw_maker_amt = round_down(amount, round_config.size)

            raw_taker_amt = raw_maker_amt * raw_price
            if decimal_places(raw_taker_amt) > round_config.amount:
                raw_taker_amt = round_up(raw_taker_amt, round_config.amount + 4)
                if decimal_places(raw_taker_amt) > round_config.amount:
                    raw_taker_amt = round_down(raw_taker_amt, round_config.amount)

            maker_amount = to_token_decimals(raw_maker_amt)
            taker_amount = to_token_decimals(raw_taker_amt)

            return SELL_SIDE, maker_amount, taker_amount
        msg = f"order_args.side must be '{BUY}' or '{SELL}'"
        raise ValueError(msg)

    def create_order(
        self,
        order_args: OrderArgs,
        options: CreateOrderOptions,
    ) -> SignedOrder:
        """Creates and signs an order."""
        side, maker_amount, taker_amount = self.get_order_amounts(
            order_args.side,
            order_args.size,
            order_args.price,
            ROUNDING_CONFIG[options.tick_size],
        )

        data = OrderData(
            maker=self.funder,
            token_id=order_args.token_id,
            maker_amount=str(maker_amount),
            taker_amount=str(taker_amount),
            side=side,
            signer=self._v2_order_signer(),
            timestamp=str(time.time_ns() // 1_000_000),
            metadata=order_args.metadata,
            builder=order_args.builder_code,
            expiration=str(order_args.expiration),
            signature_type=self.sig_type,
        )

        contract_config = get_contract_config(
            self.signer.get_chain_id(),
            options.neg_risk,
        )

        order_builder = V2OrderBuilder(
            contract_config.exchange,
            self.signer.get_chain_id(),
            self.signer,
        )

        return order_builder.build_signed_order(data)

    def create_market_order(
        self,
        order_args: MarketOrderArgs,
        options: CreateOrderOptions,
    ) -> SignedOrder:
        """Creates and signs a market order."""
        side, maker_amount, taker_amount = self.get_market_order_amounts(
            order_args.side,
            order_args.amount,
            order_args.price,
            ROUNDING_CONFIG[options.tick_size],
        )

        data = OrderData(
            maker=self.funder,
            token_id=order_args.token_id,
            maker_amount=str(maker_amount),
            taker_amount=str(taker_amount),
            side=side,
            signer=self._v2_order_signer(),
            timestamp=str(time.time_ns() // 1_000_000),
            metadata=order_args.metadata or BYTES32_ZERO,
            builder=order_args.builder_code or BYTES32_ZERO,
            expiration="0",
            signature_type=self.sig_type,
        )

        contract_config = get_contract_config(
            self.signer.get_chain_id(),
            options.neg_risk,
        )

        order_builder = V2OrderBuilder(
            contract_config.exchange,
            self.signer.get_chain_id(),
            self.signer,
        )

        return order_builder.build_signed_order(data)

    def calculate_buy_market_price(
        self,
        asks: list[
            OrderSummary
        ],  # expected to be sorted from worst to best price (high to low)
        amount_to_match: float,  # in usdc
        order_type: OrderType,
    ) -> float:
        if not asks:
            msg = "No ask orders available"
            raise LiquidityError(msg)

        amount = 0.0
        for p in reversed(asks):
            amount += float(p.size) * float(p.price)
            if amount >= amount_to_match:
                return float(p.price)

        if order_type == OrderType.FOK:
            msg = "no match"
            raise ValueError(msg)

        return float(asks[0].price)

    def calculate_sell_market_price(
        self,
        bids: list[
            OrderSummary
        ],  # expected to be sorted from worst to best price (low to high)
        amount_to_match: float,  # in shares
        order_type: OrderType,
    ) -> float:
        if not bids:
            msg = "No bid orders available"
            raise LiquidityError(msg)

        amount = 0.0
        for p in reversed(bids):
            amount += float(p.size)
            if amount >= amount_to_match:
                return float(p.price)

        if order_type == OrderType.FOK:
            msg = "no match"
            raise ValueError(msg)

        return float(bids[0].price)
