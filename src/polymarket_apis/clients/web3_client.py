from json import load
from pathlib import Path
from typing import Literal, Optional

from web3 import Web3
from web3.exceptions import ContractCustomError
from web3.middleware import ExtraDataToPOAMiddleware, SignAndSendRawMiddlewareBuilder

from ..types.common import EthAddress, Keccak256
from ..utilities.config import get_contract_config
from ..utilities.constants import ADDRESS_ZERO, HASH_ZERO, POLYGON
from ..utilities.web3.abis.custom_contract_errors import CUSTOM_ERROR_DICT
from ..utilities.web3.helpers import (
    get_index_set,
    sign_safe_transaction,
)


def _load_abi(contract_name: str) -> list:
    abi_path = (
        Path(__file__).parent.parent
        / "utilities"
        / "web3"
        / "abis"
        / f"{contract_name}.json"
    )
    with Path.open(abi_path) as f:
        return load(f)


class PolymarketWeb3Client:
    def __init__(
        self,
        private_key: str,
        signature_type: Literal[0, 1, 2] = 1,
        chain_id: Literal[137, 80002] = POLYGON,
    ):
        self.w3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self.w3.middleware_onion.inject(
            SignAndSendRawMiddlewareBuilder.build(private_key), layer=0
        )

        self.account = self.w3.eth.account.from_key(private_key)
        self.signature_type = signature_type

        self.config = get_contract_config(chain_id, neg_risk=False)
        self.neg_risk_config = get_contract_config(chain_id, neg_risk=True)

        self.usdc_address = Web3.to_checksum_address(self.config.collateral)
        self.usdc_abi = _load_abi("UChildERC20Proxy")
        self.usdc = self.contract(self.usdc_address, self.usdc_abi)

        self.conditional_tokens_address = Web3.to_checksum_address(
            self.config.conditional_tokens
        )
        self.conditional_tokens_abi = _load_abi("ConditionalTokens")
        self.conditional_tokens = self.contract(
            self.conditional_tokens_address, self.conditional_tokens_abi
        )

        self.exchange_address = Web3.to_checksum_address(self.config.exchange)
        self.exchange_abi = _load_abi("CTFExchange")
        self.exchange = self.contract(self.exchange_address, self.exchange_abi)

        self.neg_risk_exchange_address = Web3.to_checksum_address(
            self.neg_risk_config.exchange
        )
        self.neg_risk_exchange_abi = _load_abi("NegRiskCtfExchange")
        self.neg_risk_exchange = self.contract(
            self.neg_risk_exchange_address, self.neg_risk_exchange_abi
        )

        self.neg_risk_adapter_address = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"
        self.neg_risk_adapter_abi = _load_abi("NegRiskAdapter")
        self.neg_risk_adapter = self.contract(
            self.neg_risk_adapter_address, self.neg_risk_adapter_abi
        )

        self.proxy_factory_address = "0xaB45c5A4B0c941a2F231C04C3f49182e1A254052"
        self.proxy_factory_abi = _load_abi("ProxyWalletFactory")
        self.proxy_factory = self.contract(
            self.proxy_factory_address, self.proxy_factory_abi
        )

        self.safe_proxy_factory_address = "0xaacFeEa03eb1561C4e67d661e40682Bd20E3541b"
        self.safe_proxy_factory_abi = _load_abi("SafeProxyFactory")
        self.safe_proxy_factory = self.contract(
            self.safe_proxy_factory_address, self.safe_proxy_factory_abi
        )

        match self.signature_type:
            case 0:
                self.address = self.account.address
            case 1:
                self.address = self.get_poly_proxy_address()
            case 2:
                self.address = self.get_safe_proxy_address()
                self.safe_abi = _load_abi("Safe")
                self.safe = self.contract(self.address, self.safe_abi)

    def _encode_split(self, condition_id: Keccak256, amount: int) -> str:
        return self.conditional_tokens.encode_abi(
            abi_element_identifier="splitPosition",
            args=[self.usdc_address, HASH_ZERO, condition_id, [1, 2], amount],
        )

    def _encode_merge(self, condition_id: Keccak256, amount: int) -> str:
        return self.conditional_tokens.encode_abi(
            abi_element_identifier="mergePositions",
            args=[self.usdc_address, HASH_ZERO, condition_id, [1, 2], amount],
        )

    def _encode_redeem(self, condition_id: Keccak256) -> str:
        return self.conditional_tokens.encode_abi(
            abi_element_identifier="redeemPositions",
            args=[self.usdc_address, HASH_ZERO, condition_id, [1, 2]],
        )

    def _encode_redeem_neg_risk(
        self, condition_id: Keccak256, amounts: list[int]
    ) -> str:
        return self.neg_risk_adapter.encode_abi(
            abi_element_identifier="redeemPositions",
            args=[condition_id, amounts],
        )

    def _encode_convert(
        self, neg_risk_market_id: Keccak256, index_set: int, amount: int
    ) -> str:
        return self.neg_risk_adapter.encode_abi(
            abi_element_identifier="convertPositions",
            args=[neg_risk_market_id, index_set, amount],
        )

    def contract(self, address, abi):
        return self.w3.eth.contract(
            address=Web3.to_checksum_address(address),
            abi=abi,
        )

    def get_poly_proxy_address(self, address: EthAddress | None = None) -> EthAddress:
        """Get the polymarket proxy address for the current account."""
        address = address if address else self.account.address
        return self.exchange.functions.getPolyProxyWalletAddress(address).call()

    def get_safe_proxy_address(self, address: EthAddress | None = None) -> EthAddress:
        """Get the safe proxy address for the current account."""
        address = address if address else self.account.address
        return self.safe_proxy_factory.functions.computeProxyAddress(address).call()

    def get_usdc_balance(self, address: EthAddress | None = None) -> float:
        """
        Get the usdc balance of the given address.

        If no address is given, the balance of the proxy account corresponding to
        the private key is returned (i.e. Polymarket balance).
        Explicitly passing the proxy address is faster due to only one contract function call.
        """
        if address is None:
            address = self.address
        balance_res = self.usdc.functions.balanceOf(address).call()
        return float(balance_res / 1e6)

    def get_token_balance(
        self, token_id: str, address: Optional[EthAddress] = None
    ) -> float:
        """Get the token balance of the given address."""
        if not address:
            address = self.address
        balance_res = self.conditional_tokens.functions.balanceOf(
            address, int(token_id)
        ).call()
        return float(balance_res / 1e6)

    def get_token_complement(self, token_id: str) -> Optional[str]:
        """Get the complement of the given token."""
        try:
            return str(
                self.neg_risk_exchange.functions.getComplement(int(token_id)).call()
            )
        except ContractCustomError as e:
            if e.args[0] in CUSTOM_ERROR_DICT:
                try:
                    return str(
                        self.exchange.functions.getComplement(int(token_id)).call()
                    )
                except ContractCustomError as e2:
                    if e2.args[0] in CUSTOM_ERROR_DICT:
                        msg = f"{CUSTOM_ERROR_DICT[e2.args[0]]}"
                        raise ContractCustomError(
                            msg,
                        ) from e2

    def get_condition_id_neg_risk(self, question_id: Keccak256) -> Keccak256:
        """
        Get the condition id for a given question id.

        Warning: this works for neg risk markets (where the
        outcomeSlotCount is represented by the last two digits of question id). Returns a keccak256 hash of
        the oracle and question id.
        """
        return (
            "0x"
            + self.neg_risk_adapter.functions.getConditionId(question_id).call().hex()
        )

    def split_position(
        self, condition_id: Keccak256, amount: float, neg_risk: bool = True
    ):
        """Splits usdc into two complementary positions of equal size."""
        amount = int(amount * 1e6)
        data = self._encode_split(condition_id, amount)
        to = (
            self.neg_risk_adapter_address
            if neg_risk
            else self.conditional_tokens_address
        )
        nonce = self.w3.eth.get_transaction_count(self.account.address)
        transaction = {
            "nonce": nonce,
            "gasPrice": int(1.05 * self.w3.eth.gas_price),
            "gas": 1000000,
            "from": self.account.address,
        }

        match self.signature_type:
            case 0:
                contract = (
                    self.neg_risk_adapter if neg_risk else self.conditional_tokens
                )
                txn_data = contract.functions.splitPosition(
                    self.usdc_address,
                    HASH_ZERO,
                    condition_id,
                    [1, 2],
                    amount,
                ).build_transaction(transaction=transaction)
            case 1:
                proxy_txn = {
                    "typeCode": 1,
                    "to": to,
                    "value": 0,
                    "data": data,
                }
                txn_data = self.proxy_factory.functions.proxy(
                    [proxy_txn]
                ).build_transaction(transaction=transaction)
            case 2:
                safe_nonce = self.safe.functions.nonce().call()
                safe_txn = {
                    "to": to,
                    "data": data,
                    "operation": 0,  # 1 for delegatecall, 0 for call
                    "value": 0,
                }
                packed_sig = sign_safe_transaction(
                    self.account, self.safe, safe_txn, safe_nonce
                )
                txn_data = self.safe.functions.execTransaction(
                    safe_txn["to"],
                    safe_txn["value"],
                    safe_txn["data"],
                    safe_txn.get("operation", 0),
                    0,  # safeTxGas
                    0,  # baseGas
                    0,  # gasPrice
                    ADDRESS_ZERO,  # gasToken
                    ADDRESS_ZERO,  # refundReceiver
                    packed_sig,
                ).build_transaction(transaction=transaction)

        # Sign and send transaction
        signed_txn = self.account.sign_transaction(txn_data)
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        print(f"Txn hash: 0x{tx_hash_hex}")

        # Wait for transaction to be mined
        self.w3.eth.wait_for_transaction_receipt(tx_hash)

        print("Done!")

    def merge_position(
        self, condition_id: Keccak256, amount: float, neg_risk: bool = True
    ):
        """Merges two complementary positions into usdc."""
        amount = int(amount * 1e6)
        data = self._encode_merge(condition_id, amount)
        to = (
            self.neg_risk_adapter_address
            if neg_risk
            else self.conditional_tokens_address
        )
        nonce = self.w3.eth.get_transaction_count(self.account.address)
        transaction = {
            "nonce": nonce,
            "gasPrice": int(1.05 * self.w3.eth.gas_price),
            "gas": 1000000,
            "from": self.account.address,
        }

        match self.signature_type:
            case 0:
                contract = (
                    self.neg_risk_adapter if neg_risk else self.conditional_tokens
                )
                txn_data = contract.functions.mergePositions(
                    self.usdc_address,
                    HASH_ZERO,
                    condition_id,
                    [1, 2],
                    amount,
                ).build_transaction(transaction=transaction)
            case 1:
                proxy_txn = {
                    "typeCode": 1,
                    "to": to,
                    "value": 0,
                    "data": data,
                }

                txn_data = self.proxy_factory.functions.proxy(
                    [proxy_txn]
                ).build_transaction(transaction=transaction)
            case 2:
                safe_nonce = self.safe.functions.nonce().call()
                safe_txn = {
                    "to": to,
                    "data": data,
                    "operation": 0,  # 1 for delegatecall, 0 for call
                    "value": 0,
                }
                packed_sig = sign_safe_transaction(
                    self.account, self.safe, safe_txn, safe_nonce
                )
                txn_data = self.safe.functions.execTransaction(
                    safe_txn["to"],
                    safe_txn["value"],
                    safe_txn["data"],
                    safe_txn.get("operation", 0),
                    0,  # safeTxGas
                    0,  # baseGas
                    0,  # gasPrice
                    ADDRESS_ZERO,  # gasToken
                    ADDRESS_ZERO,  # refundReceiver
                    packed_sig,
                ).build_transaction(transaction=transaction)

        # Sign and send transaction
        signed_txn = self.account.sign_transaction(txn_data)
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        print(f"Txn hash: 0x{tx_hash_hex}")

        # Wait for transaction to be mined
        self.w3.eth.wait_for_transaction_receipt(tx_hash)

        print("Done!")

    def redeem_position(
        self, condition_id: Keccak256, amounts: list[float], neg_risk: bool = True
    ):
        """
        Redeem a position into usdc.

        Takes a condition id and a list of sizes in shares [x, y]
        where x is the number of shares of the first outcome
              y is the number of shares of the second outcome.
        """
        int_amounts = [int(amount * 1e6) for amount in amounts]
        data = (
            self._encode_redeem_neg_risk(condition_id, int_amounts)
            if neg_risk
            else self._encode_redeem(condition_id)
        )
        to = (
            self.neg_risk_adapter_address
            if neg_risk
            else self.conditional_tokens_address
        )
        nonce = self.w3.eth.get_transaction_count(self.account.address)
        transaction = {
            "nonce": nonce,
            "gasPrice": int(1.05 * self.w3.eth.gas_price),
            "gas": 1000000,
            "from": self.account.address,
        }

        match self.signature_type:
            case 0:
                contract = (
                    self.neg_risk_adapter if neg_risk else self.conditional_tokens
                )
                if neg_risk:
                    txn_data = contract.functions.redeemPositions(
                        condition_id, int_amounts
                    ).build_transaction(transaction=transaction)
                else:
                    txn_data = contract.functions.redeemPositions(
                        self.usdc_address,
                        HASH_ZERO,
                        condition_id,
                        [1, 2],
                    ).build_transaction(transaction=transaction)
            case 1:
                proxy_txn = {
                    "typeCode": 1,
                    "to": to,
                    "value": 0,
                    "data": data,
                }
                txn_data = self.proxy_factory.functions.proxy(
                    [proxy_txn]
                ).build_transaction(transaction=transaction)
            case 2:
                safe_nonce = self.safe.functions.nonce().call()
                safe_txn = {
                    "to": to,
                    "data": data,
                    "operation": 0,  # 1 for delegatecall, 0 for call
                    "value": 0,
                }
                packed_sig = sign_safe_transaction(
                    self.account, self.safe, safe_txn, safe_nonce
                )
                txn_data = self.safe.functions.execTransaction(
                    safe_txn["to"],
                    safe_txn["value"],
                    safe_txn["data"],
                    safe_txn.get("operation", 0),
                    0,  # safeTxGas
                    0,  # baseGas
                    0,  # gasPrice
                    ADDRESS_ZERO,  # gasToken
                    ADDRESS_ZERO,  # refundReceiver
                    packed_sig,
                ).build_transaction(transaction=transaction)

        # Sign and send transaction
        signed_txn = self.account.sign_transaction(txn_data)
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        print(f"Txn hash: 0x{tx_hash_hex}")

        # Wait for transaction to be mined
        self.w3.eth.wait_for_transaction_receipt(tx_hash)

        print("Done!")

    def convert_positions(
        self,
        question_ids: list[Keccak256],
        amount: float,
    ):
        amount = int(amount * 1e6)
        neg_risk_market_id = question_ids[0][:-2] + "00"
        data = self._encode_convert(
            neg_risk_market_id, get_index_set(question_ids), amount
        )
        to = self.neg_risk_adapter_address
        nonce = self.w3.eth.get_transaction_count(self.account.address)
        transaction = {
            "nonce": nonce,
            "gasPrice": int(1.05 * self.w3.eth.gas_price),
            "gas": 1000000,
            "from": self.account.address,
        }

        match self.signature_type:
            case 0:
                txn_data = self.neg_risk_adapter.functions.convertPositions(
                    neg_risk_market_id,
                    get_index_set(question_ids),
                    amount,
                ).build_transaction(transaction=transaction)
            case 1:
                proxy_txn = {
                    "typeCode": 1,
                    "to": to,
                    "value": 0,
                    "data": data,
                }

                txn_data = self.proxy_factory.functions.proxy(
                    [proxy_txn]
                ).build_transaction(transaction=transaction)
            case 2:
                safe_nonce = self.safe.functions.nonce().call()
                safe_txn = {
                    "to": to,
                    "data": data,
                    "operation": 0,  # 1 for delegatecall, 0 for call
                    "value": 0,
                }

                packed_sig = sign_safe_transaction(
                    self.account, self.safe, safe_txn, safe_nonce
                )
                txn_data = self.safe.functions.execTransaction(
                    safe_txn["to"],
                    safe_txn["value"],
                    safe_txn["data"],
                    safe_txn.get("operation", 0),
                    0,  # safeTxGas
                    0,  # baseGas
                    0,  # gasPrice
                    ADDRESS_ZERO,  # gasToken
                    ADDRESS_ZERO,  # refundReceiver
                    packed_sig,
                ).build_transaction(transaction=transaction)

        # Sign and send transaction
        signed_txn = self.account.sign_transaction(txn_data)
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        print(f"Txn hash: 0x{tx_hash_hex}")

        # Wait for transaction to be mined
        self.w3.eth.wait_for_transaction_receipt(tx_hash)

        print("Done!")
