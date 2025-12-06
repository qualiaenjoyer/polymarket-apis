from abc import ABC, abstractmethod
from json import dumps, load
from pathlib import Path
from typing import Literal

import httpx
from web3 import Web3
from web3.constants import MAX_INT
from web3.exceptions import ContractCustomError
from web3.middleware import (
    ExtraDataToPOAMiddleware,
    SignAndSendRawMiddlewareBuilder,
)
from web3.types import ChecksumAddress, HexStr, TxParams, Wei

from ..types.common import EthAddress, Keccak256
from ..types.web3_types import TransactionReceipt
from ..utilities.config import get_contract_config
from ..utilities.constants import ADDRESS_ZERO, HASH_ZERO, POLYGON
from ..utilities.exceptions import SafeAlreadyDeployedError
from ..utilities.signing.signer import Signer
from ..utilities.web3.abis.custom_contract_errors import CUSTOM_ERROR_DICT
from ..utilities.web3.helpers import (
    create_safe_create_signature,
    get_index_set,
    get_packed_signature,
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


class BaseWeb3Client(ABC):
    """
    Abstract base class for Polymarket Web3 clients.

    Contains all shared logic for contract interactions, encoding,
    and read operations. Subclasses implement the execution strategy.
    """

    def __init__(
        self,
        private_key: str,
        signature_type: Literal[0, 1, 2],
        chain_id: Literal[137, 80002] = POLYGON,
    ):
        self.client = httpx.Client(http2=True, timeout=30.0)
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

        self._setup_contracts()
        self._setup_address()

    def _setup_contracts(self):
        """Initialize all contract instances."""
        self.usdc_address = Web3.to_checksum_address(self.config.collateral)
        self.usdc_abi = _load_abi("UChildERC20Proxy")
        self.usdc = self._contract(self.usdc_address, self.usdc_abi)

        self.conditional_tokens_address = Web3.to_checksum_address(
            self.config.conditional_tokens
        )
        self.conditional_tokens_abi = _load_abi("ConditionalTokens")
        self.conditional_tokens = self._contract(
            self.conditional_tokens_address, self.conditional_tokens_abi
        )

        self.exchange_address = Web3.to_checksum_address(self.config.exchange)
        self.exchange_abi = _load_abi("CTFExchange")
        self.exchange = self._contract(self.exchange_address, self.exchange_abi)

        self.neg_risk_exchange_address = Web3.to_checksum_address(
            self.neg_risk_config.exchange
        )
        self.neg_risk_exchange_abi = _load_abi("NegRiskCtfExchange")
        self.neg_risk_exchange = self._contract(
            self.neg_risk_exchange_address, self.neg_risk_exchange_abi
        )

        self.neg_risk_adapter_address = Web3.to_checksum_address(
            "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"
        )
        self.neg_risk_adapter_abi = _load_abi("NegRiskAdapter")
        self.neg_risk_adapter = self._contract(
            self.neg_risk_adapter_address, self.neg_risk_adapter_abi
        )

        self.proxy_factory_address = Web3.to_checksum_address(
            "0xaB45c5A4B0c941a2F231C04C3f49182e1A254052"
        )
        self.proxy_factory_abi = _load_abi("ProxyWalletFactory")
        self.proxy_factory = self._contract(
            self.proxy_factory_address, self.proxy_factory_abi
        )

        self.safe_proxy_factory_address = Web3.to_checksum_address(
            "0xaacFeEa03eb1561C4e67d661e40682Bd20E3541b"
        )
        self.safe_proxy_factory_abi = _load_abi("SafeProxyFactory")
        self.safe_proxy_factory = self._contract(
            self.safe_proxy_factory_address, self.safe_proxy_factory_abi
        )

    def _setup_address(self):
        """Setup address based on signature type."""
        match self.signature_type:
            case 0:
                self.address = self.account.address
            case 1:
                self.address = self.get_poly_proxy_address()
            case 2:
                self.address = self.get_safe_proxy_address()
                self.safe_abi = _load_abi("Safe")
                self.safe = self._contract(self.address, self.safe_abi)

    def _contract(self, address, abi):
        """Create contract instance."""
        return self.w3.eth.contract(
            address=Web3.to_checksum_address(address),
            abi=abi,
        )

    def _encode_usdc_approve(self, address: ChecksumAddress) -> str:
        """Encode USDC approval transaction."""
        return self.usdc.encode_abi(
            abi_element_identifier="approve",
            args=[address, int(MAX_INT, base=16)],
        )

    def _encode_condition_tokens_approve(self, address: ChecksumAddress) -> str:
        """Encode conditional tokens approval transaction."""
        return self.conditional_tokens.encode_abi(
            abi_element_identifier="setApprovalForAll",
            args=[address, True],
        )

    def _encode_transfer_usdc(self, address: ChecksumAddress, amount: int) -> str:
        """Encode USDC transfer transaction."""
        return self.usdc.encode_abi(
            abi_element_identifier="transfer",
            args=[address, amount],
        )

    def _encode_transfer_token(
        self, token_id: str, address: ChecksumAddress, amount: int
    ) -> str:
        """Encode token transfer transaction."""
        return self.conditional_tokens.encode_abi(
            abi_element_identifier="safeTransferFrom",
            args=[self.address, address, int(token_id), amount, HASH_ZERO],
        )

    def _encode_split(self, condition_id: Keccak256, amount: int) -> str:
        """Encode split position transaction."""
        return self.conditional_tokens.encode_abi(
            abi_element_identifier="splitPosition",
            args=[self.usdc_address, HASH_ZERO, condition_id, [1, 2], amount],
        )

    def _encode_split_nr(self, condition_id: Keccak256, amount: int) -> str:
        """Encode split position transaction for neg risk."""
        return self.neg_risk_adapter.encode_abi(
            abi_element_identifier="splitPosition",
            args=[condition_id, amount],
        )

    def _encode_merge(self, condition_id: Keccak256, amount: int) -> str:
        """Encode merge positions transaction."""
        return self.conditional_tokens.encode_abi(
            abi_element_identifier="mergePositions",
            args=[self.usdc_address, HASH_ZERO, condition_id, [1, 2], amount],
        )

    def _encode_redeem(self, condition_id: Keccak256) -> str:
        """Encode redeem positions transaction."""
        return self.conditional_tokens.encode_abi(
            abi_element_identifier="redeemPositions",
            args=[self.usdc_address, HASH_ZERO, condition_id, [1, 2]],
        )

    def _encode_redeem_neg_risk(
        self, condition_id: Keccak256, amounts: list[int]
    ) -> str:
        """Encode redeem positions transaction for neg risk."""
        return self.neg_risk_adapter.encode_abi(
            abi_element_identifier="redeemPositions",
            args=[condition_id, amounts],
        )

    def _encode_convert(
        self, neg_risk_market_id: Keccak256, index_set: int, amount: int
    ) -> str:
        """Encode convert positions transaction."""
        return self.neg_risk_adapter.encode_abi(
            abi_element_identifier="convertPositions",
            args=[neg_risk_market_id, index_set, amount],
        )

    def _encode_proxy(self, proxy_txn) -> str:
        """Encode proxy transaction."""
        return self.proxy_factory.encode_abi(
            abi_element_identifier="proxy",
            args=[[proxy_txn]],
        )

    def get_base_address(self) -> EthAddress:
        """Get the base EOA address."""
        return self.account.address

    def get_poly_proxy_address(self, address: EthAddress | None = None) -> EthAddress:
        """Get the Polymarket proxy address."""
        address = address if address else self.account.address
        return self.exchange.functions.getPolyProxyWalletAddress(address).call()

    def get_safe_proxy_address(self, address: EthAddress | None = None) -> EthAddress:
        """Get the Safe proxy address."""
        address = address if address else self.account.address
        return self.safe_proxy_factory.functions.computeProxyAddress(address).call()

    def get_pol_balance(self) -> float:
        """Get POL balance for the base address associated with the private key."""
        return round(self.w3.eth.get_balance(self.account.address) / 10**18, 4)

    def get_usdc_balance(self, address: EthAddress | None = None) -> float:
        """
        Get USDC balance of an address.

        If no address is given, returns the balance of the instantiated client.
        """
        if address is None:
            address = self.address
        balance_res = self.usdc.functions.balanceOf(address).call()
        return float(balance_res / 1e6)

    def get_token_balance(
        self, token_id: str, address: EthAddress | None = None
    ) -> float:
        """Get token balance of an address."""
        if not address:
            address = self.address
        balance_res = self.conditional_tokens.functions.balanceOf(
            address, int(token_id)
        ).call()
        return float(balance_res / 1e6)

    def get_token_complement(self, token_id: str) -> str | None:
        """Get the complement token ID."""
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
                        raise ContractCustomError(msg) from e2
                    return None
            return None

    def get_condition_id_neg_risk(self, question_id: Keccak256) -> Keccak256:
        """
        Get condition ID for a neg risk market.

        Returns a keccak256 hash of the oracle and question id.
        """
        return (
            "0x"
            + self.neg_risk_adapter.functions.getConditionId(question_id).call().hex()
        )

    @abstractmethod
    def _execute(
        self,
        to: ChecksumAddress,
        data: str,
        operation_name: str,
        metadata: str | None = None,
    ) -> TransactionReceipt:
        """
        Execute a transaction (abstract method).

        Subclasses must implement this to define how transactions are executed
        (on-chain with gas vs gasless via relay).

        Args:
            to: Contract address to call
            data: Encoded transaction data
            operation_name: Name of operation for logging
            metadata: Optional metadata for gasless transactions

        Returns:
            TransactionReceipt

        """

    def split_position(
        self, condition_id: Keccak256, amount: float, neg_risk: bool = True
    ) -> TransactionReceipt:
        """Split USDC into two complementary positions."""
        amount_int = int(amount * 1e6)

        to = (
            self.neg_risk_adapter_address
            if neg_risk
            else self.conditional_tokens_address
        )
        data = (
            self._encode_split_nr(condition_id, amount_int)
            if neg_risk
            else self._encode_split(condition_id, amount_int)
        )

        return self._execute(to, data, "Split Position", metadata="split")

    def merge_position(
        self, condition_id: Keccak256, amount: float, neg_risk: bool = True
    ) -> TransactionReceipt:
        """Merge two complementary positions into USDC."""
        amount_int = int(amount * 1e6)

        to = (
            self.neg_risk_adapter_address
            if neg_risk
            else self.conditional_tokens_address
        )
        data = self._encode_merge(condition_id, amount_int)

        return self._execute(to, data, "Merge Position", metadata="merge")

    def redeem_position(
        self, condition_id: Keccak256, amounts: list[float], neg_risk: bool = True
    ) -> TransactionReceipt:
        """
        Redeem positions into USDC.

        Args:
            condition_id: Condition ID
            amounts: List of amounts [x, y] where x is shares of first outcome,
                     y is shares of second outcome
            neg_risk: Whether this is a neg risk market

        """
        int_amounts = [int(amount * 1e6) for amount in amounts]

        to = (
            self.neg_risk_adapter_address
            if neg_risk
            else self.conditional_tokens_address
        )
        data = (
            self._encode_redeem_neg_risk(condition_id, int_amounts)
            if neg_risk
            else self._encode_redeem(condition_id)
        )

        return self._execute(to, data, "Redeem Position", metadata="redeem")

    def convert_positions(
        self,
        question_ids: list[Keccak256],
        amount: float,
    ) -> TransactionReceipt:
        """
        Convert neg risk No positions to Yes positions and USDC.

        Args:
            question_ids: Array of question_ids representing positions to convert
            amount: Number of shares to convert

        """
        amount_int = int(amount * 1e6)
        neg_risk_market_id = question_ids[0][:-2] + "00"

        to = self.neg_risk_adapter_address
        data = self._encode_convert(
            neg_risk_market_id, get_index_set(question_ids), amount_int
        )

        return self._execute(to, data, "Convert Positions", metadata="convert")


class PolymarketWeb3Client(BaseWeb3Client):
    """
    Polymarket Web3 client for on-chain transactions (pays gas).

    Supports:
    - EOA wallets (signature_type=0)
    - Poly proxy wallets (signature_type=1)
    - Safe/Gnosis wallets (signature_type=2)
    """

    def __init__(
        self,
        private_key: str,
        signature_type: Literal[0, 1, 2] = 1,
        chain_id: Literal[137, 80002] = POLYGON,
    ):
        super().__init__(private_key, signature_type, chain_id)

    def _execute(
        self,
        to: ChecksumAddress,
        data: str,
        operation_name: str,
        metadata: str | None = None,  # noqa: ARG002
    ) -> TransactionReceipt:
        """Execute transaction on-chain with gas."""
        base_transaction = self._build_base_transaction()

        match self.signature_type:
            case 0:
                txn_data = self._build_eoa_transaction(to, data, base_transaction)
            case 1:
                txn_data = self._build_proxy_transaction(to, data, base_transaction)
            case 2:
                txn_data = self._build_safe_transaction(to, data, base_transaction)
            case _:
                msg = f"Invalid signature_type: {self.signature_type}"
                raise ValueError(msg)

        return self._execute_transaction(txn_data, operation_name)

    def _build_base_transaction(self) -> TxParams:
        """Build base transaction parameters."""
        nonce = self.w3.eth.get_transaction_count(self.account.address)
        current_gas_price: int = self.w3.eth.gas_price
        adjusted_gas_price = Wei(int(current_gas_price * 1.05))

        return {
            "nonce": nonce,
            "gasPrice": adjusted_gas_price,
            "gas": 1000000,
            "from": self.account.address,
        }

    def _build_eoa_transaction(
        self, to: ChecksumAddress, data: str, base_transaction: TxParams
    ) -> TxParams:
        """Build transaction for EOA wallet."""
        estimation_txn: TxParams = {
            "from": self.address,
            "to": to,
            "data": HexStr(data),
        }

        estimated = self.w3.eth.estimate_gas(estimation_txn)
        base_transaction["gas"] = int(estimated * 1.05)
        base_transaction["to"] = to
        base_transaction["data"] = HexStr(data)

        return base_transaction

    def _build_proxy_transaction(
        self, to: ChecksumAddress, data: str, base_transaction: TxParams
    ) -> TxParams:
        """Build transaction for Poly proxy wallet."""
        proxy_txn = {
            "typeCode": 1,
            "to": to,
            "value": 0,
            "data": data,
        }

        estimation_txn: TxParams = {
            "from": self.address,
            "to": to,
            "data": HexStr(data),
        }
        estimated = self.w3.eth.estimate_gas(estimation_txn)
        base_transaction["gas"] = int(estimated * 1.05) + 100000

        txn_data = self.proxy_factory.functions.proxy([proxy_txn]).build_transaction(
            transaction=base_transaction
        )
        return txn_data

    def _build_safe_transaction(
        self, to: ChecksumAddress, data: str, base_transaction: TxParams
    ) -> TxParams:
        """Build transaction for Safe wallet."""
        safe_nonce = self.safe.functions.nonce().call()
        safe_txn = {
            "to": to,
            "data": data,
            "operation": 0,
            "value": 0,
        }
        packed_sig = get_packed_signature(
            sign_safe_transaction(
                self.account,
                self.safe,
                safe_txn,
                safe_nonce,
            )
        )

        estimation_txn: TxParams = {
            "from": self.address,
            "to": to,
            "data": HexStr(data),
        }
        estimated = self.w3.eth.estimate_gas(estimation_txn)
        base_transaction["gas"] = int(estimated * 1.05) + 100000

        txn_data = self.safe.functions.execTransaction(
            safe_txn["to"],
            safe_txn["value"],
            safe_txn["data"],
            safe_txn.get("operation", 0),
            0,
            0,
            0,
            ADDRESS_ZERO,
            ADDRESS_ZERO,
            packed_sig,
        ).build_transaction(transaction=base_transaction)

        return txn_data

    def _execute_transaction(
        self, txn_data: TxParams, operation_name: str
    ) -> TransactionReceipt:
        """Execute transaction and wait for receipt."""
        signed_txn = self.account.sign_transaction(txn_data)
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        print(f"Txn hash: 0x{tx_hash_hex}")

        receipt_dict = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        receipt = TransactionReceipt.model_validate(receipt_dict)

        print(
            f"{operation_name} succeeded"
            if receipt.status == 1
            else f"{operation_name} failed"
        )
        print(
            f"Paid {round((receipt.gas_used * receipt.effective_gas_price) / 10**18, 3)} POL for gas"
        )

        return receipt

    def set_collateral_approval(self, spender: ChecksumAddress) -> TransactionReceipt:
        """Set approval for spender on USDC."""
        to = self.usdc_address
        data = self._encode_usdc_approve(address=spender)
        return self._execute(to, data, "Collateral Approval")

    def set_conditional_tokens_approval(
        self, spender: ChecksumAddress
    ) -> TransactionReceipt:
        """Set approval for spender on conditional tokens."""
        to = self.conditional_tokens_address
        data = self._encode_condition_tokens_approve(address=spender)
        return self._execute(to, data, "Conditional Tokens Approval")

    def set_all_approvals(self) -> list[TransactionReceipt]:
        """Set all necessary approvals."""
        receipts = []
        print("Approving ConditionalTokens as spender on USDC")
        receipts.append(
            self.set_collateral_approval(spender=self.conditional_tokens_address)
        )
        print("Approving CTFExchange as spender on USDC")
        receipts.append(self.set_collateral_approval(spender=self.exchange_address))
        print("Approving NegRiskCtfExchange as spender on USDC")
        receipts.append(
            self.set_collateral_approval(spender=self.neg_risk_exchange_address)
        )
        print("Approving NegRiskAdapter as spender on USDC")
        receipts.append(
            self.set_collateral_approval(spender=self.neg_risk_adapter_address)
        )
        print("Approving CTFExchange as spender on ConditionalTokens")
        receipts.append(
            self.set_conditional_tokens_approval(spender=self.exchange_address)
        )
        print("Approving NegRiskCtfExchange as spender on ConditionalTokens")
        receipts.append(
            self.set_conditional_tokens_approval(spender=self.neg_risk_exchange_address)
        )
        print("Approving NegRiskAdapter as spender on ConditionalTokens")
        receipts.append(
            self.set_conditional_tokens_approval(spender=self.neg_risk_adapter_address)
        )
        print("All approvals set!")
        return receipts

    def transfer_usdc(self, recipient: EthAddress, amount: float) -> TransactionReceipt:
        """Transfer USDC to recipient."""
        balance = self.get_usdc_balance(address=self.address)
        if balance < amount:
            msg = f"Insufficient USDC balance: {balance} < {amount}"
            raise ValueError(msg)

        amount_int = int(amount * 1e6)
        to = self.usdc_address
        data = self._encode_transfer_usdc(
            self.w3.to_checksum_address(recipient), amount_int
        )
        return self._execute(to, data, "USDC Transfer")

    def transfer_token(
        self, token_id: str, recipient: EthAddress, amount: float
    ) -> TransactionReceipt:
        """Transfer conditional token to recipient."""
        balance = self.get_token_balance(token_id=token_id, address=self.address)
        if balance < amount:
            msg = f"Insufficient token balance: {balance} < {amount}"
            raise ValueError(msg)

        amount_int = int(amount * 1e6)
        to = self.conditional_tokens_address
        data = self._encode_transfer_token(
            token_id, self.w3.to_checksum_address(recipient), amount_int
        )
        return self._execute(to, data, "Token Transfer")

    def deploy_safe(self) -> TransactionReceipt:
        """Deploy a Safe wallet."""
        safe_address = self.get_safe_proxy_address()
        if self.w3.eth.get_code(self.w3.to_checksum_address(safe_address)) != b"":
            msg = f"Safe already deployed at {safe_address}"
            raise SafeAlreadyDeployedError(msg)

        sig = create_safe_create_signature(account=self.account, chain_id=POLYGON)
        split_sig = split_signature(sig)

        base_transaction = self._build_base_transaction()
        txn_data = self.safe_proxy_factory.functions.createProxy(
            ADDRESS_ZERO,
            0,
            ADDRESS_ZERO,
            (split_sig["v"], split_sig["r"], split_sig["s"]),
        ).build_transaction(transaction=base_transaction)

        return self._execute_transaction(txn_data, "Gnosis Safe Deployment")


class PolymarketGaslessWeb3Client(BaseWeb3Client):
    """
    Polymarket Web3 client for gasless transactions via relay.

    Only supports Safe/Gnosis wallets (signature_type=2) currently.
    Poly proxy support (signature_type=1) coming soon.

    Requires builder API credentials for relay authentication.
    """

    def __init__(
        self,
        private_key: str,
        signature_type: Literal[2] = 2,
        chain_id: Literal[137, 80002] = POLYGON,
    ):
        if signature_type != 2:
            msg = "PolymarketGaslessWeb3Client currently only supports signature_type=2 (Safe wallets). Poly proxy support (signature_type=1) coming soon."
            raise ValueError(msg)

        super().__init__(private_key, signature_type, chain_id)

        # Setup for gasless transactions
        self.signer = Signer(private_key=private_key, chain_id=chain_id)
        self.relay_url = "https://relayer-v2.polymarket.com"
        self.sign_url = "https://builder-signing-server.vercel.app/sign"

    def _execute(
        self,
        to: ChecksumAddress,
        data: str,
        operation_name: str,
        metadata: str | None = None,
    ) -> TransactionReceipt:
        """Execute transaction via gasless relay."""
        body = self._build_safe_relay_transaction(to, data, metadata or "")

        payload = {
            "method": "POST",
            "path": "/submit",
            "body": dumps(body),
        }

        headers_response = self.client.post(self.sign_url, json=payload)
        headers_response.raise_for_status()

        headers = headers_response.json()

        url = f"{self.relay_url}/submit"
        response = self.client.post(
            url, headers=headers, content=dumps(body).encode("utf-8")
        )
        response.raise_for_status()

        gasless_response = response.json()

        print(
            f"Gasless txn submitted: {gasless_response.get('transactionHash', 'N/A')}"
        )
        print(f"Transaction ID: {gasless_response.get('transactionID', 'N/A')}")
        print(f"State: {gasless_response.get('state', 'N/A')}")

        # Wait for confirmation and return receipt
        tx_hash = gasless_response.get("transactionHash")
        if tx_hash:
            receipt_dict = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            receipt = TransactionReceipt.model_validate(receipt_dict)

            print(
                f"{operation_name} succeeded"
                if receipt.status == 1
                else f"{operation_name} failed"
            )

            return receipt
        msg = f"No transaction hash in response: {gasless_response}"
        raise ValueError(msg)

    def _get_relay_nonce(self, wallet_type: Literal["PROXY", "SAFE"]) -> int:
        """Get nonce from relay for Safe wallet."""
        url = f"{self.relay_url}/nonce"
        params = {
            "address": self.get_base_address(),
            "type": wallet_type,
        }
        response = self.client.get(url, params=params)
        response.raise_for_status()
        return int(response.json()["nonce"])

    def _build_safe_relay_transaction(
        self, to: ChecksumAddress, data: str, metadata: str
    ) -> dict:
        """Build Safe relay transaction body."""
        safe_nonce = self._get_relay_nonce(wallet_type="SAFE")

        safe_txn = {
            "to": to,
            "data": data,
            "operation": 0,
            "value": 0,
        }

        signature = sign_safe_transaction(
            self.account,
            self.safe,
            safe_txn,
            safe_nonce,
        ).signature.hex()

        match signature[-2:]:
            case "00" | "1b":
                signature = signature[:-2] + "1f"
            case "01" | "1c":
                signature = signature[:-2] + "20"

        return {
            "data": safe_txn["data"],
            "from": self.get_base_address(),
            "metadata": metadata,
            "nonce": str(safe_nonce),
            "proxyWallet": self.get_safe_proxy_address(),
            "signature": "0x" + signature,
            "signatureParams": {
                "baseGas": "0",
                "gasPrice": "0",
                "gasToken": ADDRESS_ZERO,
                "operation": "0",
                "refundReceiver": ADDRESS_ZERO,
                "safeTxnGas": "0",
            },
            "to": to,
            "type": "SAFE",
        }
