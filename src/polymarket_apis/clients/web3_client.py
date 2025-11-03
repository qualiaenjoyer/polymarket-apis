from json import load
from pathlib import Path
from typing import Literal

from web3 import Web3
from web3.constants import MAX_INT
from web3.exceptions import ContractCustomError
from web3.middleware import (
    ExtraDataToPOAMiddleware,
    SignAndSendRawMiddlewareBuilder,
)
from web3.types import ChecksumAddress, TxParams, Wei

from ..types.common import EthAddress, Keccak256
from ..utilities.config import get_contract_config
from ..utilities.constants import ADDRESS_ZERO, HASH_ZERO, POLYGON
from ..utilities.exceptions import SafeAlreadyDeployedError
from ..utilities.web3.abis.custom_contract_errors import CUSTOM_ERROR_DICT
from ..utilities.web3.helpers import (
    create_safe_create_signature,
    get_index_set,
    sign_safe_transaction,
    split_signature,
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
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)  # type: ignore[arg-type]
        self.w3.middleware_onion.inject(
            SignAndSendRawMiddlewareBuilder.build(private_key),  # type: ignore[arg-type]
            layer=0,
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

        self.neg_risk_adapter_address = Web3.to_checksum_address(
            "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"
        )
        self.neg_risk_adapter_abi = _load_abi("NegRiskAdapter")
        self.neg_risk_adapter = self.contract(
            self.neg_risk_adapter_address, self.neg_risk_adapter_abi
        )

        self.proxy_factory_address = Web3.to_checksum_address(
            "0xaB45c5A4B0c941a2F231C04C3f49182e1A254052"
        )
        self.proxy_factory_abi = _load_abi("ProxyWalletFactory")
        self.proxy_factory = self.contract(
            self.proxy_factory_address, self.proxy_factory_abi
        )

        self.safe_proxy_factory_address = Web3.to_checksum_address(
            "0xaacFeEa03eb1561C4e67d661e40682Bd20E3541b"
        )
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

    def _encode_usdc_approve(self, address: ChecksumAddress) -> str:
        return self.usdc.encode_abi(
            abi_element_identifier="approve",
            args=[address, int(MAX_INT, base=16)],
        )

    def _encode_condition_tokens_approve(self, address: ChecksumAddress) -> str:
        return self.conditional_tokens.encode_abi(
            abi_element_identifier="setApprovalForAll",
            args=[address, True],
        )

    def _encode_transfer_usdc(self, address: ChecksumAddress, amount: int) -> str:
        return self.usdc.encode_abi(
            abi_element_identifier="transfer",
            args=[address, amount],
        )

    def _encode_transfer_token(
        self, token_id: str, address: ChecksumAddress, amount: int
    ) -> str:
        return self.conditional_tokens.encode_abi(
            abi_element_identifier="safeTransferFrom",
            args=[self.address, address, int(token_id), amount, HASH_ZERO],
        )

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

    def _build_transaction(self) -> TxParams:
        """Build base transaction parameters."""
        nonce = self.w3.eth.get_transaction_count(self.account.address)

        current_gas_price: int = self.w3.eth.gas_price
        adjusted_gas_price = Wei(int(current_gas_price * 1.05))

        transaction: TxParams = {
            "nonce": nonce,
            "gasPrice": adjusted_gas_price,
            "gas": 1000000,
            "from": self.account.address,
        }

        return transaction

    def _set_collateral_approval(self, spender: ChecksumAddress) -> str:
        data = self._encode_usdc_approve(address=spender)
        transaction = self._build_transaction()
        txn_data: TxParams | None = None

        match self.signature_type:
            case 0:
                txn_data = self.usdc.functions.approve(
                    spender, int(MAX_INT, base=16)
                ).build_transaction(transaction=transaction)
            case 1:
                proxy_txn = {
                    "typeCode": 1,
                    "to": self.usdc_address,
                    "value": 0,
                    "data": data,
                }
                txn_data = self.proxy_factory.functions.proxy(
                    [proxy_txn]
                ).build_transaction(transaction=transaction)
            case 2:
                safe_nonce = self.safe.functions.nonce().call()
                safe_txn = {
                    "to": self.usdc_address,
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

        signed_txn = self.account.sign_transaction(txn_data)
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        print(f"Txn hash: 0x{tx_hash_hex}")

        # Wait for transaction to be mined
        self.w3.eth.wait_for_transaction_receipt(tx_hash)

        print("Done!")

        return f"0x{tx_hash_hex}"

    def _set_conditional_tokens_approval(self, spender: ChecksumAddress) -> str:
        data = self._encode_condition_tokens_approve(address=spender)
        transaction = self._build_transaction()
        txn_data: TxParams | None = None

        match self.signature_type:
            case 0:
                txn_data = self.conditional_tokens.functions.setApprovalForAll(
                    spender, True
                ).build_transaction(transaction=transaction)
            case 1:
                proxy_txn = {
                    "typeCode": 1,
                    "to": self.conditional_tokens_address,
                    "value": 0,
                    "data": data,
                }
                txn_data = self.proxy_factory.functions.proxy(
                    [proxy_txn]
                ).build_transaction(transaction=transaction)
            case 2:
                safe_nonce = self.safe.functions.nonce().call()
                safe_txn = {
                    "to": self.conditional_tokens_address,
                    "data": data,
                    "operation": 0,  # 1 for delegatecall, 0 for call
                    "value": 0,
                }
                packed_sig = sign_safe_transaction(
                    self.account,
                    self.safe,
                    safe_txn,
                    safe_nonce,
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

        signed_txn = self.account.sign_transaction(txn_data)
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        print(f"Txn hash: 0x{tx_hash_hex}")

        # Wait for transaction to be mined
        self.w3.eth.wait_for_transaction_receipt(tx_hash)

        print("Done!")

        return f"0x{tx_hash_hex}"

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
        self, token_id: str, address: EthAddress | None = None
    ) -> float:
        """Get the token balance of the given address."""
        if not address:
            address = self.address
        balance_res = self.conditional_tokens.functions.balanceOf(
            address, int(token_id)
        ).call()
        return float(balance_res / 1e6)

    def get_token_complement(self, token_id: str) -> str | None:
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
                    return None
            return None

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

    def deploy_safe(self) -> str:
        """Deploy a Safe wallet using the SafeProxyFactory contract."""
        safe_address = self.get_safe_proxy_address()
        if self.w3.eth.get_code(self.w3.to_checksum_address(safe_address)) != b"":
            msg = f"Safe already deployed at {safe_address}"
            raise SafeAlreadyDeployedError(msg)

        # Create the EIP-712 signature for Safe creation
        sig = create_safe_create_signature(account=self.account, chain_id=POLYGON)

        # Split the signature into r, s, v components
        split_sig = split_signature(sig)

        # Build the transaction
        transaction = self._build_transaction()

        # Execute the createProxy function
        txn_data = self.safe_proxy_factory.functions.createProxy(
            ADDRESS_ZERO,  # paymentToken
            0,  # payment
            ADDRESS_ZERO,  # paymentReceiver
            (
                split_sig["v"],
                split_sig["r"],
                split_sig["s"],
            ),  # createSig tuple (uint8, bytes32, bytes32)
        ).build_transaction(transaction=transaction)

        # Sign and send transaction
        signed_txn = self.account.sign_transaction(txn_data)
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        print(f"txn hash: 0x{tx_hash_hex}")

        # Wait for transaction to be mined
        self.w3.eth.wait_for_transaction_receipt(tx_hash)

        print("Done!")

        return f"0x{tx_hash_hex}"

    def set_all_approvals(self) -> None:
        """Sets both collateral and conditional tokens approvals."""
        print("Approving ConditionalTokens as spender on USDC")
        self._set_collateral_approval(
            spender=self.conditional_tokens_address,
        )
        print("Approving CTFExchange as spender on USDC")
        self._set_collateral_approval(
            spender=self.exchange_address,
        )
        print("Approving NegRiskCtfExchange as spender on USDC")
        self._set_collateral_approval(
            spender=self.neg_risk_exchange_address,
        )
        print("Approving NegRiskAdapter as spender on USDC")
        self._set_collateral_approval(
            spender=self.neg_risk_adapter_address,
        )
        print("Approving CTFExchange as spender on ConditionalTokens")
        self._set_conditional_tokens_approval(
            spender=self.exchange_address,
        )
        print("Approving NegRiskCtfExchange as spender on ConditionalTokens")
        self._set_conditional_tokens_approval(
            spender=self.neg_risk_exchange_address,
        )
        print("Approving NegRiskAdapter as spender on ConditionalTokens")
        self._set_conditional_tokens_approval(
            spender=self.neg_risk_adapter_address,
        )
        print("All approvals set!")

    def transfer_usdc(self, recipient: EthAddress, amount: float) -> str:
        """Transfers usdc.e from the account to the proxy address."""
        balance = self.get_usdc_balance(address=self.address)
        if balance < amount:
            msg = f"Insufficient USDC.e balance: {balance} < {amount}"
            raise ValueError(msg)
        amount = int(balance * 1e6)
        transaction = self._build_transaction()
        data = self._encode_transfer_usdc(
            self.w3.to_checksum_address(recipient), amount
        )
        txn_data: TxParams | None = None
        match self.signature_type:
            case 0:
                txn_data = self.usdc.functions.transfer(
                    recipient,
                    amount,
                ).build_transaction(transaction=transaction)
            case 1:
                proxy_txn = {
                    "typeCode": 1,
                    "to": self.usdc_address,
                    "value": 0,
                    "data": data,
                }
                txn_data = self.proxy_factory.functions.proxy(
                    [proxy_txn]
                ).build_transaction(transaction=transaction)
            case 2:
                safe_nonce = self.safe.functions.nonce().call()
                safe_txn = {
                    "to": self.usdc_address,
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

        return f"0x{tx_hash_hex}"

    def transfer_token(
        self, token_id: str, recipient: EthAddress, amount: float
    ) -> str:
        """Transfers conditional tokens from the account to the recipient address."""
        balance = self.get_token_balance(token_id=token_id, address=self.address)
        if balance < amount:
            msg = f"Insufficient token balance: {balance} < {amount}"
            raise ValueError(msg)
        amount = int(balance * 1e6)
        transaction = self._build_transaction()
        data = self._encode_transfer_token(
            token_id, self.w3.to_checksum_address(recipient), amount
        )
        txn_data: TxParams | None = None
        match self.signature_type:
            case 0:
                txn_data = self.conditional_tokens.functions.safeTransferFrom(
                    self.address,
                    recipient,
                    int(token_id),
                    amount,
                    b"",
                ).build_transaction(transaction=transaction)
            case 1:
                proxy_txn = {
                    "typeCode": 1,
                    "to": self.conditional_tokens_address,
                    "value": 0,
                    "data": data,
                }
                txn_data = self.proxy_factory.functions.proxy(
                    [proxy_txn]
                ).build_transaction(transaction=transaction)
            case 2:
                safe_nonce = self.safe.functions.nonce().call()
                safe_txn = {
                    "to": self.conditional_tokens_address,
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

        return f"0x{tx_hash_hex}"

    def split_position(
        self, condition_id: Keccak256, amount: float, neg_risk: bool = True
    ) -> str:
        """Splits usdc into two complementary positions of equal size."""
        amount = int(amount * 1e6)
        data = self._encode_split(condition_id, amount)
        to = (
            self.neg_risk_adapter_address
            if neg_risk
            else self.conditional_tokens_address
        )
        transaction = self._build_transaction()
        txn_data: TxParams | None = None

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

        return f"0x{tx_hash_hex}"

    def merge_position(
        self, condition_id: Keccak256, amount: float, neg_risk: bool = True
    ) -> str:
        """Merges two complementary positions into usdc."""
        amount = int(amount * 1e6)
        data = self._encode_merge(condition_id, amount)
        to = (
            self.neg_risk_adapter_address
            if neg_risk
            else self.conditional_tokens_address
        )
        transaction = self._build_transaction()
        txn_data: TxParams | None = None

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

        return f"0x{tx_hash_hex}"

    def redeem_position(
        self, condition_id: Keccak256, amounts: list[float], neg_risk: bool = True
    ) -> str:
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
        transaction = self._build_transaction()
        txn_data: TxParams | None = None

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

        return f"0x{tx_hash_hex}"

    def convert_positions(
        self,
        question_ids: list[Keccak256],
        amount: float,
    ) -> str:
        amount = int(amount * 1e6)
        neg_risk_market_id = question_ids[0][:-2] + "00"
        data = self._encode_convert(
            neg_risk_market_id, get_index_set(question_ids), amount
        )
        to = self.neg_risk_adapter_address
        transaction = self._build_transaction()
        txn_data: TxParams | None = None

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

        return f"0x{tx_hash_hex}"
