from py_order_utils.builders import OrderBuilder as UtilsOrderBuilder
from py_order_utils.model import (
    BUY as UTILS_BUY,
)
from py_order_utils.model import (
    EOA,
    OrderData,
    SignedOrder,
)
from py_order_utils.model import (
    SELL as UTILS_SELL,
)
from py_order_utils.signer import Signer as UtilsSigner

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
from ..constants import BUY, SELL
from ..exceptions import LiquidityError
from ..signing.signer import Signer
from .helpers import (
    decimal_places,
    round_down,
    round_normal,
    round_up,
    to_token_decimals,
)

ROUNDING_CONFIG: dict[TickSize, RoundConfig] = {
    "0.1": RoundConfig(price=1, size=2, amount=3),
    "0.01": RoundConfig(price=2, size=2, amount=4),
    "0.001": RoundConfig(price=3, size=2, amount=5),
    "0.0001": RoundConfig(price=4, size=2, amount=6),
}


class OrderBuilder:
    def __init__(self, signer: Signer, sig_type=None, funder=None):
        self.signer = signer

        # Signature type used sign orders, defaults to EOA type
        self.sig_type = sig_type if sig_type is not None else EOA

        # Address which holds funds to be used.
        # Used for Polymarket proxy wallets and other smart contract wallets
        # Defaults to the address of the signer
        self.funder = funder if funder is not None else self.signer.address()

    def get_order_amounts(
            self, side: str, size: float, price: float, round_config: RoundConfig,
    ):
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

            return UTILS_BUY, maker_amount, taker_amount
        if side == SELL:
            raw_maker_amt = round_down(size, round_config.size)

            raw_taker_amt = raw_maker_amt * raw_price
            if decimal_places(raw_taker_amt) > round_config.amount:
                raw_taker_amt = round_up(raw_taker_amt, round_config.amount + 4)
                if decimal_places(raw_taker_amt) > round_config.amount:
                    raw_taker_amt = round_down(raw_taker_amt, round_config.amount)

            maker_amount = to_token_decimals(raw_maker_amt)
            taker_amount = to_token_decimals(raw_taker_amt)

            return UTILS_SELL, maker_amount, taker_amount
        msg = f"order_args.side must be '{BUY}' or '{SELL}'"
        raise ValueError(msg)

    def get_market_order_amounts(
            self, side: str, amount: float, price: float, round_config: RoundConfig,
    ):
        raw_price = round_normal(price, round_config.price)

        if side == BUY:
            raw_maker_amt = round_down(amount, round_config.size)
            raw_taker_amt = raw_maker_amt / raw_price
            if decimal_places(raw_taker_amt) > round_config.amount:
                raw_taker_amt = round_up(raw_taker_amt, round_config.amount + 4)
                if decimal_places(raw_taker_amt) > round_config.amount:
                    raw_taker_amt = round_down(raw_taker_amt, round_config.amount)

            maker_amount = to_token_decimals(raw_maker_amt)
            taker_amount = to_token_decimals(raw_taker_amt)

            return UTILS_BUY, maker_amount, taker_amount

        if side == SELL:
            raw_maker_amt = round_down(amount, round_config.size)

            raw_taker_amt = raw_maker_amt * raw_price
            if decimal_places(raw_taker_amt) > round_config.amount:
                raw_taker_amt = round_up(raw_taker_amt, round_config.amount + 4)
                if decimal_places(raw_taker_amt) > round_config.amount:
                    raw_taker_amt = round_down(raw_taker_amt, round_config.amount)

            maker_amount = to_token_decimals(raw_maker_amt)
            taker_amount = to_token_decimals(raw_taker_amt)

            return UTILS_SELL, maker_amount, taker_amount
        msg = f"order_args.side must be '{BUY}' or '{SELL}'"
        raise ValueError(msg)

    def create_order(
            self, order_args: OrderArgs, options: CreateOrderOptions,
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
            taker=order_args.taker,
            tokenId=order_args.token_id,
            makerAmount=str(maker_amount),
            takerAmount=str(taker_amount),
            side=side,
            feeRateBps=str(order_args.fee_rate_bps),
            nonce=str(order_args.nonce),
            signer=self.signer.address(),
            expiration=str(order_args.expiration),
            signatureType=self.sig_type,
        )

        contract_config = get_contract_config(
            self.signer.get_chain_id(), options.neg_risk,
        )

        order_builder = UtilsOrderBuilder(
            contract_config.exchange,
            self.signer.get_chain_id(),
            UtilsSigner(key=self.signer.private_key),
        )

        return order_builder.build_signed_order(data)

    def create_market_order(
            self, order_args: MarketOrderArgs, options: CreateOrderOptions,
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
            taker=order_args.taker,
            tokenId=order_args.token_id,
            makerAmount=str(maker_amount),
            takerAmount=str(taker_amount),
            side=side,
            feeRateBps=str(order_args.fee_rate_bps),
            nonce=str(order_args.nonce),
            signer=self.signer.address(),
            expiration="0",
            signatureType=self.sig_type,
        )

        contract_config = get_contract_config(
            self.signer.get_chain_id(), options.neg_risk,
        )

        order_builder = UtilsOrderBuilder(
            contract_config.exchange,
            self.signer.get_chain_id(),
            UtilsSigner(key=self.signer.private_key),
        )

        return order_builder.build_signed_order(data)

    def calculate_buy_market_price(
            self,
            asks: list[OrderSummary], # expected to be sorted from worst to best price (high to low)
            amount_to_match: float, # in usdc
            order_type: OrderType,
    ) -> float:
        if not asks:
            msg = "No ask orders available"
            raise LiquidityError(msg)

        sum = 0
        for p in reversed(asks):
            sum += float(p.size) * float(p.price)
            if sum >= amount_to_match:
                return float(p.price)

        if order_type == OrderType.FOK:
            msg = "no match"
            raise ValueError(msg)

        return float(asks[0].price)

    def calculate_sell_market_price(
            self,
            bids: list[OrderSummary], # expected to be sorted from worst to best price (low to high)
            amount_to_match: float, # in shares
            order_type: OrderType,
    ) -> float:
        if not bids:
            msg = "No bid orders available"
            raise LiquidityError(msg)

        sum = 0
        for p in reversed(bids):
            sum += float(p.size)
            if sum >= amount_to_match:
                return float(p.price)

        if order_type == OrderType.FOK:
            msg = "no match"
            raise ValueError(msg)

        return float(bids[0].price)
