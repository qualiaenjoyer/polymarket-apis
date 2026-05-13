import logging
from abc import ABC, abstractmethod
from json import dumps, load
from pathlib import Path
from time import sleep, time
from typing import Any, Literal, Optional, cast

import httpx
from eth_account.messages import encode_defunct
from eth_typing import ABI, AnyAddress, ChecksumAddress, HexStr
from web3 import Web3
from web3.constants import MAX_INT
from web3.eth import Contract
from web3.exceptions import ContractCustomError, TimeExhausted
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import Nonce, TxParams, Wei

from ..types.clob_types import ApiCreds, RequestArgs
from ..types.common import EthAddress, Keccak256
from ..types.web3_types import DepositWalletCall, TransactionReceipt
from ..utilities._internal_log import (
    current_or_new_trace_id,
    emit,
    get_logger,
    log_extra,
)
from ..utilities.config import get_contract_config
from ..utilities.constants import (
    ADDRESS_ZERO,
    DEPOSIT_WALLET_DOMAIN_NAME,
    DEPOSIT_WALLET_DOMAIN_VERSION,
    HASH_ZERO,
    POLYGON,
)
from ..utilities.exceptions import (
    SafeAlreadyDeployedError,
    TransactionFailedError,
    TransactionTimeoutError,
)
from ..utilities.headers import create_level_2_headers, create_relayer_headers
from ..utilities.signing.signer import Signer
from ..utilities.web3.abis.custom_contract_errors import CUSTOM_ERROR_DICT
from ..utilities.web3.helpers import (
    SafeTxn,
    create_proxy_struct,
    create_safe_create_signature,
    derive_deposit_wallet,
    get_index_set,
    get_packed_signature,
    get_signature_type_from_runtime_code,
    sign_safe_transaction,
    split_signature,
)

logger = get_logger(__name__)


def _display_decimal(value: Any, max_decimals: int = 6) -> str:
    return f"{float(value):.{max_decimals}f}".rstrip("0").rstrip(".")


def _web3_action(operation_name: str) -> str:
    return operation_name.replace(" Position", "").replace(" Positions", "").upper()


def _load_abi(contract_name: str) -> ABI:
    abi_path = (
        Path(__file__).parent.parent
        / "utilities"
        / "web3"
        / "abis"
        / f"{contract_name}.json"
    )
    with Path.open(abi_path) as f:
        return cast("ABI", load(f))


class NonceManager:
    """Thread-safe in-memory nonce tracker to avoid nonce collisions."""

    def __init__(self, w3: Web3, address: str) -> None:
        self.w3 = w3
        self.address = Web3.to_checksum_address(address)
        self._pending: int | None = None

    def next(self) -> int:
        chain_nonce = self.w3.eth.get_transaction_count(self.address, "pending")
        if self._pending is None or chain_nonce > self._pending:
            self._pending = chain_nonce
        else:
            self._pending += 1
        return self._pending

    def reset(self) -> None:
        self._pending = None


class BaseWeb3Client(ABC):
    """
    Abstract base class for Polymarket Web3 clients.

    Contains all shared logic for contract interactions, encoding,
    and read operations. Subclasses implement the execution strategy.
    """

    def __init__(
        self,
        private_key: HexStr,
        signature_type: Literal[0, 1, 2, 3],
        chain_id: Literal[137, 80002] = POLYGON,
        rpc_url: str = "https://tenderly.rpc.polygon.community",
        proxy: Optional[str] = None,
        *,
        logger: Optional[Any] = None,
    ):
        self.client = httpx.Client(http2=True, timeout=30.0, proxy=proxy)
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        self.account = self.w3.eth.account.from_key(private_key)
        self.signature_type = signature_type
        self.logger = logger or get_logger(f"{__name__}.{id(self)}")

        self.config = get_contract_config(chain_id, neg_risk=False)
        self.neg_risk_config = get_contract_config(chain_id, neg_risk=True)
        self.chain_id = chain_id
        self._nonce_manager = NonceManager(self.w3, self.account.address)
        self._setup_contracts()
        self._setup_address()

    def _setup_contracts(self) -> None:
        """Initialize all contract instances."""
        self.pusd_address = Web3.to_checksum_address(self.config.collateral)
        self.pusd_abi = _load_abi("CollateralToken")
        self.pusd = self._contract(self.pusd_address, self.pusd_abi)

        self.usdc_e_address = Web3.to_checksum_address(
            "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        )

        self.collateral_onramp_address = Web3.to_checksum_address(
            "0x93070a847efEf7F70739046A929D47a521F5B8ee"
        )

        self.conditional_tokens_address = Web3.to_checksum_address(
            self.config.conditional_tokens
        )
        self.conditional_tokens_abi = _load_abi("ConditionalTokens")
        self.conditional_tokens = self._contract(
            self.conditional_tokens_address, self.conditional_tokens_abi
        )

        self.ctf_collateral_adapter_address = Web3.to_checksum_address(
            "0xada100db00ca00073811820692005400218fce1f"
        )
        self.ctf_collateral_adapter_abi = _load_abi("CtfCollateralAdapter")
        self.ctf_collateral_adapter = self._contract(
            self.ctf_collateral_adapter_address, self.ctf_collateral_adapter_abi
        )

        self.neg_risk_ctf_collateral_adapter = Web3.to_checksum_address(
            "0xada2005600dec949baf300f4c6120000bdb6eaab"
        )
        self.neg_risk_ctf_collateral_abi = _load_abi("NegRiskCtfCollateralAdapter")
        self.neg_risk_ctf_collateral = self._contract(
            self.neg_risk_ctf_collateral_adapter, self.neg_risk_ctf_collateral_abi
        )

        self.ctf_auto_redeem_address = Web3.to_checksum_address(
            "0xF3cFb6a6eBFeB51876289Eb235719EB1C65252B0"
        )
        self.ctf_auto_redeem = self._contract(
            self.ctf_auto_redeem_address, _load_abi("CtfAutoRedeem")
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
            self.config.neg_risk_adapter
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

        self.deposit_wallet_factory_address = Web3.to_checksum_address(
            "0x00000000000Fb5C9ADea0298D729A0CB3823Cc07"
        )
        self.deposit_wallet_implementation_address = Web3.to_checksum_address(
            "0x58CA52ebe0DadfdF531Cde7062e76746de4Db1eB"
        )

        self.multisend_address = Web3.to_checksum_address(
            "0xa238cbeb142c10ef7ad8442c6d1f9e89e07e7761"
        )
        self.multisend_abi = _load_abi("MultiSend")
        self.multisend = self._contract(self.multisend_address, self.multisend_abi)

    def _setup_address(self) -> None:
        """Setup address based on signature type."""
        match self.signature_type:
            case 0:
                self.address = self.account.address
            case 1:
                self.address = self.get_poly_proxy_wallet_address()
            case 2:
                self.address = self.get_safe_proxy_wallet_address()
                self.safe_abi = _load_abi("Safe")
                self.safe = self._contract(self.address, self.safe_abi)
            case 3:
                self.address = self.get_expected_deposit_wallet()

    def _contract(self, address: AnyAddress | str | bytes, abi: ABI) -> Contract:
        """Create contract instance."""
        return self.w3.eth.contract(
            address=Web3.to_checksum_address(address),
            abi=abi,
        )

    def _encode_erc20_approve(
        self, address: ChecksumAddress, amount: int | None = None
    ) -> str:
        """Encode ERC-20 approval transaction."""
        abi = self.pusd.encode_abi(
            abi_element_identifier="approve",
            args=[address, int(MAX_INT, base=16) if amount is None else amount],
        )
        return cast("str", abi)

    def _encode_condition_tokens_approve(
        self, address: ChecksumAddress, approved: bool = True
    ) -> str:
        """Encode conditional tokens approval transaction."""
        abi = self.conditional_tokens.encode_abi(
            abi_element_identifier="setApprovalForAll",
            args=[address, approved],
        )
        return cast("str", abi)

    def _encode_transfer_pusd(self, address: ChecksumAddress, amount: int) -> str:
        """Encode pUSD transfer transaction."""
        abi = self.pusd.encode_abi(
            abi_element_identifier="transfer",
            args=[address, amount],
        )
        return cast("str", abi)

    def _encode_transfer_token(
        self, token_id: str, address: ChecksumAddress, amount: int
    ) -> str:
        """Encode token transfer transaction."""
        abi = self.conditional_tokens.encode_abi(
            abi_element_identifier="safeTransferFrom",
            args=[self.address, address, int(token_id), amount, HASH_ZERO],
        )
        return cast("str", abi)

    def _encode_split(self, condition_id: Keccak256, amount: int) -> str:
        """Encode split position transaction."""
        abi = self.conditional_tokens.encode_abi(
            abi_element_identifier="splitPosition",
            args=[self.pusd_address, HASH_ZERO, condition_id, [1, 2], amount],
        )
        return cast("str", abi)

    def _encode_merge(self, condition_id: Keccak256, amount: int) -> str:
        """Encode merge positions transaction."""
        abi = self.conditional_tokens.encode_abi(
            abi_element_identifier="mergePositions",
            args=[self.pusd_address, HASH_ZERO, condition_id, [1, 2], amount],
        )
        return cast("str", abi)

    def _encode_redeem(self, condition_id: Keccak256) -> str:
        """Encode redeem positions transaction."""
        abi = self.ctf_collateral_adapter.encode_abi(
            abi_element_identifier="redeemPositions",
            args=[self.pusd_address, HASH_ZERO, condition_id, [1, 2]],
        )
        return cast("str", abi)

    def _encode_redeem_neg_risk(
        self, condition_id: Keccak256, amounts: list[int]
    ) -> str:
        """Encode redeem positions transaction for neg risk."""
        abi = self.neg_risk_adapter.encode_abi(
            abi_element_identifier="redeemPositions",
            args=[condition_id, amounts],
        )
        return cast("str", abi)

    def _encode_convert(
        self, neg_risk_market_id: Keccak256, index_set: int, amount: int
    ) -> str:
        """Encode convert positions transaction."""
        abi = self.neg_risk_adapter.encode_abi(
            abi_element_identifier="convertPositions",
            args=[neg_risk_market_id, index_set, amount],
        )
        return cast("str", abi)

    def _encode_proxy(self, proxy_txn: dict[str, object]) -> str:
        """Encode proxy transaction."""
        return self._encode_proxy_calls([proxy_txn])

    def _encode_proxy_calls(self, proxy_txns: list[dict[str, object]]) -> str:
        """Encode one or more proxy transactions."""
        abi = self.proxy_factory.encode_abi(
            abi_element_identifier="proxy",
            args=[proxy_txns],
        )
        return cast("str", abi)

    def _encode_multisend(self, calls: list[dict[str, object]]) -> str:
        """Encode Safe MultiSend payload for a list of CALL operations."""
        encoded_transactions = b""
        for call in calls:
            data = cast("str", call["data"]).removeprefix("0x")
            encoded_transactions += (
                b"\x00"
                + bytes.fromhex(cast("str", call["to"]).removeprefix("0x"))
                + int(cast("int", call.get("value", 0))).to_bytes(32, "big")
                + (len(data) // 2).to_bytes(32, "big")
                + bytes.fromhex(data)
            )

        abi = self.multisend.encode_abi(
            abi_element_identifier="multiSend",
            args=[encoded_transactions],
        )
        return cast("str", abi)

    def get_base_wallet_address(self) -> EthAddress:
        """Get the base EOA address."""
        return cast("EthAddress", self.account.address)

    def get_base_address(self) -> EthAddress:
        """Compatibility alias for the base EOA address."""
        return self.get_base_wallet_address()

    def get_poly_proxy_wallet_address(
        self, address: EthAddress | None = None
    ) -> EthAddress:
        """Get the Polymarket proxy address."""
        address = address or self.account.address
        result = self.exchange.functions.getProxyWalletAddress(address).call()
        return cast("EthAddress", result)

    def get_safe_proxy_wallet_address(
        self, address: EthAddress | None = None
    ) -> EthAddress:
        """Get the Safe proxy address."""
        address = address or self.account.address
        result = self.safe_proxy_factory.functions.computeProxyAddress(address).call()
        return cast("EthAddress", result)

    def get_deposit_wallet_address(self) -> EthAddress:
        """Get the expected deposit wallet address."""
        return derive_deposit_wallet(
            self.account.address,
            self.deposit_wallet_factory_address,
            self.deposit_wallet_implementation_address,
        )

    def get_expected_deposit_wallet(self) -> EthAddress:
        """Compatibility alias for the expected deposit wallet address."""
        return self.get_deposit_wallet_address()

    def detect_wallet_signature_type(
        self, address: EthAddress
    ) -> Literal[0, 1, 2, 3] | None:
        """
        Detect wallet signature type from an address.

        Returns:
            - 0 for EOA / undeployed smart contract computed address
            - 1 for Polymarket proxy wallet
            - 2 for Safe/Gnosis proxy wallet
            - 3 for Deposit wallet

        """
        code = (
            self.w3.eth.get_code(self.w3.to_checksum_address(address))
            .hex()
            .removeprefix("0x")
            .lower()
        )
        return get_signature_type_from_runtime_code(code)

    def get_pol_balance(self) -> float:
        """Get POL balance for the base address associated with the private key."""
        return round(self.w3.eth.get_balance(self.account.address) / 10**18, 4)

    def get_pusd_balance(self, address: EthAddress | None = None) -> float:
        """
        Get pUSD balance of an address.

        If no address is given, returns the balance of the instantiated client.
        """
        if address is None:
            address = self.address
        balance_res = self.pusd.functions.balanceOf(address).call()
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
        keccak = (
            "0x"
            + self.neg_risk_adapter.functions.getConditionId(question_id).call().hex()
        )
        return cast("Keccak256", keccak)

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
        self, condition_id: Keccak256, amount: float, neg_risk: bool
    ) -> TransactionReceipt:
        """Split pUSD into two complementary positions."""
        trace_id = current_or_new_trace_id()
        emit(
            self.logger,
            logging.INFO,
            "web3.position.split.requested",
            "SPLIT %s pUSD condition_id=%s neg_risk=%s",
            _display_decimal(amount),
            condition_id,
            neg_risk,
            operation="split_position",
            web3_action="SPLIT",
            phase="requested",
            condition_id=condition_id,
            amount=amount,
            atomic_amount=int(amount * 1e6),
            neg_risk=neg_risk,
            trace_id=trace_id,
        )
        amount_int = int(amount * 1e6)

        to = (
            self.neg_risk_adapter_address
            if neg_risk
            else self.ctf_collateral_adapter_address
        )
        data = self._encode_split(condition_id, amount_int)

        return self._execute(to, data, "Split Position", metadata="split")

    def merge_position(
        self, condition_id: Keccak256, amount: float, neg_risk: bool
    ) -> TransactionReceipt:
        """Merge two complementary positions into pUSD."""
        trace_id = current_or_new_trace_id()
        emit(
            self.logger,
            logging.INFO,
            "web3.position.merge.requested",
            "MERGE %s shares condition_id=%s neg_risk=%s",
            _display_decimal(amount),
            condition_id,
            neg_risk,
            operation="merge_position",
            web3_action="MERGE",
            phase="requested",
            condition_id=condition_id,
            amount=amount,
            atomic_amount=int(amount * 1e6),
            neg_risk=neg_risk,
            trace_id=trace_id,
        )
        amount_int = int(amount * 1e6)

        to = (
            self.neg_risk_adapter_address
            if neg_risk
            else self.ctf_collateral_adapter_address
        )
        data = self._encode_merge(condition_id, amount_int)

        return self._execute(to, data, "Merge Position", metadata="merge")

    def redeem_position(
        self, condition_id: Keccak256, amounts: list[float], neg_risk: bool
    ) -> TransactionReceipt:
        """
        Redeem positions into pUSD.

        Args:
            condition_id: Condition ID
            amounts: List of amounts [x, y] where x is shares of first outcome,
                     y is shares of second outcome
            neg_risk: Whether this is a neg risk market

        """
        trace_id = current_or_new_trace_id()
        emit(
            self.logger,
            logging.INFO,
            "web3.position.redeem.requested",
            "REDEEM amounts=%s condition_id=%s neg_risk=%s",
            [_display_decimal(amount) for amount in amounts],
            condition_id,
            neg_risk,
            operation="redeem_position",
            web3_action="REDEEM",
            phase="requested",
            condition_id=condition_id,
            amounts=amounts,
            atomic_amounts=[int(amount * 1e6) for amount in amounts],
            neg_risk=neg_risk,
            trace_id=trace_id,
        )
        int_amounts = [int(amount * 1e6) for amount in amounts]

        to = (
            self.neg_risk_adapter_address
            if neg_risk
            else self.ctf_collateral_adapter_address
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
        Convert neg risk No positions to Yes positions and pUSD.

        Args:
            question_ids: Array of question_ids representing positions to convert
            amount: Number of shares to convert

        """
        trace_id = current_or_new_trace_id()
        emit(
            self.logger,
            logging.INFO,
            "web3.position.convert.requested",
            "CONVERT %s shares question_ids=%s",
            _display_decimal(amount),
            question_ids,
            operation="convert_positions",
            web3_action="CONVERT",
            phase="requested",
            question_ids=question_ids,
            amount=amount,
            atomic_amount=int(amount * 1e6),
            trace_id=trace_id,
        )
        amount_int = int(amount * 1e6)
        neg_risk_market_id = question_ids[0][:-2] + "00"

        to = self.neg_risk_adapter_address
        data = self._encode_convert(
            neg_risk_market_id, get_index_set(question_ids), amount_int
        )

        return self._execute(to, data, "Convert Positions", metadata="convert")

    def auto_redeem_enable(self) -> TransactionReceipt:
        """Enable CTF auto-redeem as a ConditionalTokens operator."""
        trace_id = current_or_new_trace_id()
        self.logger.info(
            "Enabling auto-redeem",
            extra=log_extra(trace_id=trace_id),
        )
        data = self._encode_condition_tokens_approve(
            address=self.ctf_auto_redeem_address,
            approved=True,
        )
        return self._execute(
            self.conditional_tokens_address,
            data,
            "Auto Redeem Enable",
            metadata="auto_redeem_enable",
        )

    def auto_redeem_disable(self) -> TransactionReceipt:
        """Disable CTF auto-redeem as a ConditionalTokens operator."""
        trace_id = current_or_new_trace_id()
        self.logger.info(
            "Disabling auto-redeem",
            extra=log_extra(trace_id=trace_id),
        )
        data = self._encode_condition_tokens_approve(
            address=self.ctf_auto_redeem_address,
            approved=False,
        )
        return self._execute(
            self.conditional_tokens_address,
            data,
            "Auto Redeem Disable",
            metadata="auto_redeem_disable",
        )

    def set_collateral_approval(self, spender: ChecksumAddress) -> TransactionReceipt:
        """Set approval for spender on pUSD collateral."""
        trace_id = current_or_new_trace_id()
        self.logger.info(
            "Setting collateral approval: spender=%s",
            spender,
            extra=log_extra(spender=spender, trace_id=trace_id),
        )
        data = self._encode_erc20_approve(address=spender)
        return self._execute(
            self.pusd_address,
            data,
            "Collateral Approval",
            metadata="collateral_approval",
        )

    def set_conditional_tokens_approval(
        self, spender: ChecksumAddress
    ) -> TransactionReceipt:
        """Set approval for spender on conditional tokens."""
        trace_id = current_or_new_trace_id()
        self.logger.info(
            "Setting conditional tokens approval: spender=%s",
            spender,
            extra=log_extra(spender=spender, trace_id=trace_id),
        )
        data = self._encode_condition_tokens_approve(address=spender)
        return self._execute(
            self.conditional_tokens_address,
            data,
            "Conditional Tokens Approval",
            metadata="conditional_tokens_approval",
        )

    def _approval_calls(self, approving: bool = True) -> list[dict[str, object]]:
        erc20_approval_amount = int(MAX_INT, base=16) if approving else 0
        action = "Approving" if approving else "Revoking"
        pusd_spenders = {
            self.conditional_tokens_address: "ConditionalTokens",
            self.ctf_collateral_adapter_address: "CtfCollateralAdapter",
            self.neg_risk_ctf_collateral_adapter: "NegRiskCtfCollateralAdapter",
            self.exchange_address: "CTFExchange V2",
            self.neg_risk_exchange_address: "NegRiskCtfExchange V2",
            self.neg_risk_adapter_address: "NegRiskAdapter",
        }
        ctf_spenders = {
            self.ctf_collateral_adapter_address: "CtfCollateralAdapter",
            self.neg_risk_ctf_collateral_adapter: "NegRiskCtfCollateralAdapter",
            self.exchange_address: "CTFExchange V2",
            self.neg_risk_exchange_address: "NegRiskCtfExchange V2",
            self.neg_risk_adapter_address: "NegRiskAdapter",
        }

        calls: list[dict[str, object]] = []
        for spender, name in pusd_spenders.items():
            self.logger.debug("%s %s as spender on pUSD", action, name)
            calls.append(
                {
                    "to": self.pusd_address,
                    "data": self._encode_erc20_approve(
                        address=spender,
                        amount=erc20_approval_amount,
                    ),
                }
            )

        self.logger.debug("%s CollateralOnramp as spender on USDC.e", action)
        calls.append(
            {
                "to": self.usdc_e_address,
                "data": self._encode_erc20_approve(
                    self.collateral_onramp_address,
                    amount=erc20_approval_amount,
                ),
            }
        )

        for spender, name in ctf_spenders.items():
            self.logger.debug("%s %s as spender on ConditionalTokens", action, name)
            calls.append(
                {
                    "to": self.conditional_tokens_address,
                    "data": self._encode_condition_tokens_approve(
                        address=spender,
                        approved=approving,
                    ),
                }
            )
        return calls

    def _execute_calls(
        self,
        calls: list[dict[str, object]],
        operation_name: str,
        metadata: str | None = None,
    ) -> list[TransactionReceipt]:
        """Execute calls sequentially by default."""
        return [
            self._execute(
                cast("ChecksumAddress", call["to"]),
                cast("str", call["data"]),
                operation_name,
                metadata=metadata,
            )
            for call in calls
        ]

    def set_all_approvals(self) -> list[TransactionReceipt]:
        """Set all necessary approvals."""
        trace_id = current_or_new_trace_id()
        self.logger.info(
            "Setting all approvals",
            extra=log_extra(trace_id=trace_id),
        )
        receipts = self._execute_calls(
            self._approval_calls(),
            "Set All Approvals",
            metadata="set_all_approvals",
        )
        self.logger.info(
            "All approvals set successfully: %d transactions",
            len(receipts),
            extra=log_extra(receipt_count=len(receipts), trace_id=trace_id),
        )
        return receipts

    def set_all_disapprovals(self) -> list[TransactionReceipt]:
        """Revoke all approvals managed by set_all_approvals."""
        trace_id = current_or_new_trace_id()
        self.logger.info(
            "Revoking all approvals",
            extra=log_extra(trace_id=trace_id),
        )
        receipts = self._execute_calls(
            self._approval_calls(approving=False),
            "Set All Disapprovals",
            metadata="set_all_disapprovals",
        )
        self.logger.info(
            "All approvals revoked successfully: %d transactions",
            len(receipts),
            extra=log_extra(receipt_count=len(receipts), trace_id=trace_id),
        )
        return receipts

    def transfer_pusd(self, recipient: EthAddress, amount: float) -> TransactionReceipt:
        """Transfer pUSD to recipient."""
        trace_id = current_or_new_trace_id()
        balance = self.get_pusd_balance(address=self.address)
        if balance < amount:
            self.logger.error(
                "Insufficient pUSD balance: %.6f < %.6f",
                balance,
                amount,
                extra=log_extra(balance=balance, amount=amount, trace_id=trace_id),
            )
            msg = f"Insufficient pUSD balance: {balance} < {amount}"
            raise ValueError(msg)

        amount_int = int(amount * 1e6)
        self.logger.info(
            "Transferring %.6f pUSD to %s",
            amount,
            recipient,
            extra=log_extra(amount=amount, recipient=recipient, trace_id=trace_id),
        )
        data = self._encode_transfer_pusd(
            self.w3.to_checksum_address(recipient), amount_int
        )
        return self._execute(
            self.pusd_address,
            data,
            "pUSD Transfer",
            metadata="pusd_transfer",
        )

    def transfer_token(
        self, token_id: str, recipient: EthAddress, amount: float
    ) -> TransactionReceipt:
        """Transfer conditional token to recipient."""
        trace_id = current_or_new_trace_id()
        balance = self.get_token_balance(token_id=token_id, address=self.address)
        if balance < amount:
            self.logger.error(
                "Insufficient token balance: %.6f < %.6f",
                balance,
                amount,
                extra=log_extra(balance=balance, amount=amount, token_id=token_id, trace_id=trace_id),
            )
            msg = f"Insufficient token balance: {balance} < {amount}"
            raise ValueError(msg)

        amount_int = int(amount * 1e6)
        self.logger.info(
            "Transferring %.6f of token %s to %s",
            amount,
            token_id,
            recipient,
            extra=log_extra(amount=amount, token_id=token_id, recipient=recipient, trace_id=trace_id),
        )
        data = self._encode_transfer_token(
            token_id, self.w3.to_checksum_address(recipient), amount_int
        )
        return self._execute(
            self.conditional_tokens_address,
            data,
            "Token Transfer",
            metadata="token_transfer",
        )


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
        private_key: HexStr,
        signature_type: Literal[0, 1, 2],
        chain_id: Literal[137, 80002] = POLYGON,
        rpc_url: str = "https://tenderly.rpc.polygon.community",
        proxy: Optional[str] = None,
        *,
        logger: Optional[Any] = None,
    ):
        super().__init__(
            private_key, signature_type, chain_id=chain_id, rpc_url=rpc_url, proxy=proxy, logger=logger
        )

    def _execute(
        self,
        to: ChecksumAddress,
        data: str,
        operation_name: str,
        metadata: str | None = None,
    ) -> TransactionReceipt:
        """Execute transaction on-chain with gas."""
        trace_id = current_or_new_trace_id()
        start = time()
        tx_hash_hex = "unknown"

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

        try:
            signed_txn = self.account.sign_transaction(txn_data)
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            tx_hash_hex = f"0x{tx_hash.hex()}"

            emit(
                self.logger,
                logging.INFO,
                "web3.tx.submitted",
                "Transaction submitted: tx_hash=%s operation=%s nonce=%s gas_price=%s",
                tx_hash_hex,
                operation_name,
                txn_data.get("nonce"),
                txn_data.get("gasPrice"),
                phase="submitted",
                tx_hash=tx_hash_hex,
                operation=operation_name,
                nonce=txn_data.get("nonce"),
                gas_price=txn_data.get("gasPrice"),
                metadata=metadata,
                trace_id=trace_id,
                chain_id=self.chain_id,
                wallet_address=self.address,
                wallet_type=self.signature_type,
                contract_address=to,
            )

            receipt_dict = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        except TimeExhausted as exc:
            latency_ms = round((time() - start) * 1000, 3)
            emit(
                self.logger,
                logging.ERROR,
                "web3.tx.timeout",
                "Transaction timed out: tx_hash=%s operation=%s latency_ms=%.3f",
                tx_hash_hex,
                operation_name,
                latency_ms,
                phase="timeout",
                success=False,
                tx_hash=tx_hash_hex,
                operation=operation_name,
                latency_ms=latency_ms,
                error_type=type(exc).__name__,
                error_detail=str(exc),
                metadata=metadata,
                trace_id=trace_id,
                chain_id=self.chain_id,
                wallet_address=self.address,
                wallet_type=self.signature_type,
                contract_address=to,
            )
            msg = f"{operation_name} timed out waiting for confirmation"
            raise TransactionTimeoutError(
                msg,
                tx_hash=tx_hash_hex,
            ) from exc

        except Exception as exc:
            latency_ms = round((time() - start) * 1000, 3)
            emit(
                self.logger,
                logging.ERROR,
                "web3.tx.error",
                "Transaction error: tx_hash=%s operation=%s error=%s latency_ms=%.3f",
                tx_hash_hex,
                operation_name,
                type(exc).__name__,
                latency_ms,
                phase="error",
                success=False,
                tx_hash=tx_hash_hex,
                operation=operation_name,
                error_type=type(exc).__name__,
                error_detail=str(exc),
                latency_ms=latency_ms,
                metadata=metadata,
                trace_id=trace_id,
                chain_id=self.chain_id,
                wallet_address=self.address,
                wallet_type=self.signature_type,
                contract_address=to,
            )
            raise
        else:
            receipt = TransactionReceipt.model_validate(receipt_dict)
            latency_ms = round((time() - start) * 1000, 3)
            gas_cost_pol = round(
                (receipt.gas_used * receipt.effective_gas_price) / 10**18, 6
            )

            if receipt.status == 1:
                emit(
                    self.logger,
                    logging.INFO,
                    "web3.tx.confirmed",
                    "Transaction confirmed: tx_hash=%s block=%d gas_used=%d gas_cost=%.6f latency_ms=%.3f",
                    tx_hash_hex,
                    receipt.block_number,
                    receipt.gas_used,
                    gas_cost_pol,
                    latency_ms,
                    phase="confirmed",
                    success=True,
                    tx_hash=tx_hash_hex,
                    operation=operation_name,
                    block_number=receipt.block_number,
                    gas_used=receipt.gas_used,
                    gas_cost_pol=gas_cost_pol,
                    latency_ms=latency_ms,
                    status="success",
                    metadata=metadata,
                    trace_id=trace_id,
                    chain_id=self.chain_id,
                    wallet_address=self.address,
                    wallet_type=self.signature_type,
                    contract_address=to,
                )
            else:
                emit(
                    self.logger,
                    logging.ERROR,
                    "web3.tx.failed",
                    "Transaction failed on-chain: tx_hash=%s block=%d status=%d",
                    tx_hash_hex,
                    receipt.block_number,
                    receipt.status,
                    phase="failed",
                    success=False,
                    tx_hash=tx_hash_hex,
                    operation=operation_name,
                    block_number=receipt.block_number,
                    status="failed",
                    metadata=metadata,
                    trace_id=trace_id,
                    chain_id=self.chain_id,
                    wallet_address=self.address,
                    wallet_type=self.signature_type,
                    contract_address=to,
                )
                msg = f"{operation_name} failed on-chain"
                raise TransactionFailedError(
                    msg,
                    tx_hash=tx_hash_hex,
                    nonce=txn_data.get("nonce"),
                )

            return receipt

    def _build_base_transaction(self) -> TxParams:
        """Build base transaction parameters with managed nonce."""
        nonce = self._nonce_manager.next()
        current_gas_price: int = self.w3.eth.gas_price
        adjusted_gas_price = Wei(int(current_gas_price * 1.05))

        return {
            "nonce": cast("Nonce", nonce),
            "gasPrice": adjusted_gas_price,
            "gas": 1000000,
            "from": self.account.address,
            "chainId": self.chain_id,
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
        proxy_txn: dict[str, object] = {
            "typeCode": 1,
            "to": to,
            "value": 0,
            "data": data,
        }

        return self._build_proxy_batch_transaction([proxy_txn], base_transaction)

    def _build_proxy_batch_transaction(
        self, proxy_txns: list[dict[str, object]], base_transaction: TxParams
    ) -> TxParams:
        """Build transaction for one or more Poly proxy wallet calls."""
        encoded_txn = self._encode_proxy_calls(proxy_txns)
        estimation_txn: TxParams = {
            "from": self.account.address,
            "to": self.proxy_factory_address,
            "data": HexStr(encoded_txn),
        }
        estimated = self.w3.eth.estimate_gas(estimation_txn)
        base_transaction["gas"] = int(estimated * 1.05)

        txn_data = self.proxy_factory.functions.proxy(proxy_txns).build_transaction(
            transaction=base_transaction
        )
        return txn_data

    def _build_safe_transaction(
        self,
        to: ChecksumAddress,
        data: str,
        base_transaction: TxParams,
        operation: int = 0,
    ) -> TxParams:
        """Build transaction for Safe wallet."""
        safe_nonce = self.safe.functions.nonce().call()
        safe_txn: SafeTxn = {
            "to": to,
            "data": data,
            "operation": operation,
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

        estimated = self.w3.eth.estimate_gas(
            cast("TxParams", {k: v for k, v in txn_data.items() if k != "gas"})
        )
        txn_data["gas"] = int(estimated * 1.05) + 100000

        return txn_data

    def _execute_calls(
        self,
        calls: list[dict[str, object]],
        operation_name: str,
        metadata: str | None = None,
    ) -> list[TransactionReceipt]:
        """Execute a batch of calls when the wallet type supports batching."""
        base_transaction = self._build_base_transaction()

        match self.signature_type:
            case 0:
                return super()._execute_calls(calls, operation_name, metadata)
            case 1:
                proxy_txns = [
                    {
                        "typeCode": 1,
                        "to": call["to"],
                        "value": call.get("value", 0),
                        "data": call["data"],
                    }
                    for call in calls
                ]
                txn_data = self._build_proxy_batch_transaction(
                    proxy_txns, base_transaction
                )
            case 2:
                txn_data = self._build_safe_transaction(
                    self.multisend_address,
                    self._encode_multisend(calls),
                    base_transaction,
                    operation=1,
                )
            case _:
                msg = f"Invalid signature_type: {self.signature_type}"
                raise ValueError(msg)

        return [self._execute_transaction(txn_data, operation_name)]

    def _execute_transaction(
        self, txn_data: TxParams, operation_name: str
    ) -> TransactionReceipt:
        """Execute transaction and wait for receipt — DEPRECATED, use _execute instead."""
        return self._execute(
            cast("ChecksumAddress", txn_data.get("to")),
            cast("str", txn_data.get("data")),
            operation_name,
        )

    def deploy_safe_wallet(self) -> TransactionReceipt:
        """Deploy a Safe wallet."""
        safe_address = self.get_safe_proxy_wallet_address()
        if self.w3.eth.get_code(self.w3.to_checksum_address(safe_address)) != b"":
            msg = f"Safe already deployed at {safe_address}"
            raise SafeAlreadyDeployedError(msg)

        sig = create_safe_create_signature(account=self.account, chain_id=self.chain_id)
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
    """Polymarket Web3 client for gasless transactions via relay."""

    DEFAULT_DEPOSIT_WALLET_DEADLINE_SECONDS = 240

    def __init__(
        self,
        private_key: HexStr,
        signature_type: Literal[1, 2, 3],
        *,
        relayer_api_key: str | None = None,
        builder_creds: ApiCreds | None = None,
        chain_id: Literal[137, 80002] = POLYGON,
        rpc_url: str = "https://tenderly.rpc.polygon.community",
        proxy: Optional[str] = None,
        logger: Optional[Any] = None,
    ):
        if signature_type not in {1, 2, 3}:
            msg = (
                "PolymarketGaslessWeb3Client only supports signature_type=1 "
                "(Poly proxy wallets), signature_type=2 (Safe wallets), and "
                "signature_type=3 (Deposit wallets)."
            )
            raise ValueError(msg)
        if relayer_api_key is None and builder_creds is None:
            msg = "PolymarketGaslessWeb3Client requires either relayer_api_key or builder_creds."
            raise ValueError(msg)

        super().__init__(
            private_key, signature_type, chain_id=chain_id, rpc_url=rpc_url, proxy=proxy, logger=logger
        )

        # Setup for gasless transactions
        self.signer = Signer(private_key=private_key, chain_id=chain_id)
        self.relay_url = "https://relayer-v2.polymarket.com"
        self.relay_hub = "0xD216153c06E857cD7f72665E0aF1d7D82172F494"
        self.relay_address = "0x7db63fe6d62eb73fb01f8009416f4c2bb4fbda6a"
        self.relayer_api_key = relayer_api_key
        self.builder_creds = builder_creds

    def _execute(
        self,
        to: ChecksumAddress,
        data: str,
        operation_name: str,
        metadata: str | None = None,
    ) -> TransactionReceipt:
        """Execute transaction via gasless relay."""
        trace_id = current_or_new_trace_id()
        start = time()
        web3_action = _web3_action(operation_name)

        match self.signature_type:
            case 1:
                body = self._build_proxy_relay_transaction(to, data, metadata or "")
            case 2:
                body = self._build_safe_relay_transaction(to, data, metadata or "")
            case 3:
                body = self._build_deposit_relay_transaction(to, data, metadata or "")
            case _:
                msg = f"Invalid signature_type: {self.signature_type}"
                raise ValueError(msg)

        try:
            return self._submit_relay_transaction(
                body,
                operation_name,
                trace_id,
                start,
                web3_action=web3_action,
            )
        except Exception as exc:
            latency_ms = round((time() - start) * 1000, 3)
            emit(
                self.logger,
                logging.ERROR,
                "web3.relay_tx.error",
                "%s relay error=%s in %.2fms",
                web3_action,
                type(exc).__name__,
                latency_ms,
                phase="error",
                success=False,
                operation=operation_name,
                web3_action=web3_action,
                error_type=type(exc).__name__,
                error_detail=str(exc),
                latency_ms=latency_ms,
                metadata=metadata,
                trace_id=trace_id,
                chain_id=self.chain_id,
                wallet_address=self.address,
                wallet_type=self.signature_type,
                contract_address=to,
            )
            raise

    def _submit_relay_transaction(
        self,
        body: dict[str, Any],
        operation_name: str,
        trace_id: str,
        start: float,
        *,
        web3_action: str | None = None,
    ) -> TransactionReceipt:
        """Submit a prepared relay transaction body and wait for a receipt."""
        web3_action = web3_action or _web3_action(operation_name)
        url = f"{self.relay_url}/submit"
        content = dumps(body).encode("utf-8")
        headers = self._create_relay_headers("/submit", "POST", content.decode())

        response = self.client.post(url, headers=headers, content=content)
        response.raise_for_status()

        gasless_response = response.json()
        tx_hash = gasless_response.get("transactionHash")
        transaction_id = gasless_response.get("transactionID")

        emit(
            self.logger,
            logging.INFO,
            "web3.relay_tx.submitted",
            "%s submitted tx_hash=%s tx_id=%s state=%s",
            web3_action,
            tx_hash or "N/A",
            transaction_id or "N/A",
            gasless_response.get("state", "N/A"),
            phase="submitted",
            tx_hash=tx_hash,
            transaction_id=transaction_id,
            state=gasless_response.get("state"),
            operation=operation_name,
            web3_action=web3_action,
            trace_id=trace_id,
            chain_id=self.chain_id,
            wallet_address=self.address,
            wallet_type=self.signature_type,
        )

        if tx_hash:
            receipt_dict = self.w3.eth.wait_for_transaction_receipt(
                cast("HexStr", tx_hash), timeout=120
            )
            receipt = TransactionReceipt.model_validate(receipt_dict)
            latency_ms = round((time() - start) * 1000, 3)

            if receipt.status == 1:
                emit(
                    self.logger,
                    logging.INFO,
                    "web3.relay_tx.confirmed",
                    "%s confirmed tx_hash=%s block=%d in %.2fms",
                    web3_action,
                    tx_hash,
                    receipt.block_number,
                    latency_ms,
                    phase="confirmed",
                    success=True,
                    tx_hash=tx_hash,
                    block_number=receipt.block_number,
                    gas_used=receipt.gas_used,
                    latency_ms=latency_ms,
                    operation=operation_name,
                    web3_action=web3_action,
                    status="success",
                    trace_id=trace_id,
                    chain_id=self.chain_id,
                    wallet_address=self.address,
                    wallet_type=self.signature_type,
                )
            else:
                emit(
                    self.logger,
                    logging.ERROR,
                    "web3.relay_tx.failed",
                    "%s failed tx_hash=%s block=%d",
                    web3_action,
                    tx_hash,
                    receipt.block_number,
                    phase="failed",
                    success=False,
                    tx_hash=tx_hash,
                    block_number=receipt.block_number,
                    operation=operation_name,
                    web3_action=web3_action,
                    status="failed",
                    trace_id=trace_id,
                    chain_id=self.chain_id,
                    wallet_address=self.address,
                    wallet_type=self.signature_type,
                )
                msg = f"{operation_name} failed on-chain (gasless)"
                raise TransactionFailedError(
                    msg,
                    tx_hash=tx_hash,
                )
            return receipt

        if transaction_id:
            tx_hash = self._wait_for_relay_transaction_hash(
                str(transaction_id), trace_id, start
            )
            if tx_hash:
                receipt_dict = self.w3.eth.wait_for_transaction_receipt(
                    cast("HexStr", tx_hash), timeout=120
                )
                receipt = TransactionReceipt.model_validate(receipt_dict)
                latency_ms = round((time() - start) * 1000, 3)

                if receipt.status == 1:
                    emit(
                        self.logger,
                    logging.INFO,
                    "web3.relay_tx.confirmed",
                    "%s confirmed tx_hash=%s block=%d in %.2fms",
                    web3_action,
                    tx_hash,
                    receipt.block_number,
                        latency_ms,
                        phase="confirmed",
                        success=True,
                        tx_hash=tx_hash,
                        block_number=receipt.block_number,
                        gas_used=receipt.gas_used,
                        latency_ms=latency_ms,
                        operation=operation_name,
                        web3_action=web3_action,
                        status="success",
                        trace_id=trace_id,
                        chain_id=self.chain_id,
                        wallet_address=self.address,
                        wallet_type=self.signature_type,
                    )
                else:
                    emit(
                        self.logger,
                    logging.ERROR,
                    "web3.relay_tx.failed",
                    "%s failed tx_hash=%s block=%d",
                    web3_action,
                    tx_hash,
                        receipt.block_number,
                        phase="failed",
                        success=False,
                        tx_hash=tx_hash,
                        block_number=receipt.block_number,
                        operation=operation_name,
                        web3_action=web3_action,
                        status="failed",
                        trace_id=trace_id,
                        chain_id=self.chain_id,
                        wallet_address=self.address,
                        wallet_type=self.signature_type,
                    )
                    msg = f"{operation_name} failed on-chain (gasless)"
                    raise TransactionFailedError(
                        msg,
                        tx_hash=tx_hash,
                    )
                return receipt

        msg = f"No transaction hash in response: {gasless_response}"
        raise ValueError(msg)

    def _create_relay_headers(
        self, request_path: str, method: Literal["POST"], body: str
    ) -> dict[str, str]:
        """Create headers for either relayer_api_key or builder_creds."""
        if self.relayer_api_key is not None:
            return create_relayer_headers(
                self.relayer_api_key,
                self.get_base_wallet_address(),
            )

        if self.builder_creds is None:
            msg = "Missing relayer_api_key. Provide relayer_api_key or builder_creds."
            raise ValueError(msg)

        return create_level_2_headers(
            self.signer,
            self.builder_creds,
            RequestArgs(method=method, request_path=request_path, body=body),
            builder=True,
        )

    def _wait_for_relay_transaction_hash(
        self, transaction_id: str, trace_id: str, start: float
    ) -> str | None:
        """Poll the relayer until it attaches an on-chain transaction hash."""
        url = f"{self.relay_url}/transaction"
        for attempt in range(100):
            response = self.client.get(url, params={"id": transaction_id})
            response.raise_for_status()
            transactions = response.json()
            transaction = transactions[0] if transactions else {}
            state = transaction.get("state")

            if state == "STATE_FAILED":
                emit(
                    self.logger,
                    logging.ERROR,
                    "web3.relay_tx.failed",
                    "Gasless transaction failed in relayer: tx_id=%s state=%s attempt=%d",
                    transaction_id,
                    state,
                    attempt,
                    phase="failed",
                    success=False,
                    transaction_id=transaction_id,
                    state=state,
                    attempt=attempt,
                    trace_id=trace_id,
                )
                msg = f"Gasless transaction failed in relayer: {transaction}"
                raise ValueError(msg)

            tx_hash = transaction.get("transactionHash")
            if tx_hash:
                latency_ms = round((time() - start) * 1000, 3)
                emit(
                    self.logger,
                    logging.INFO,
                    "web3.relay_tx.hash_attached",
                    "Relayer attached tx hash: tx_id=%s tx_hash=%s latency_ms=%.3f",
                    transaction_id,
                    tx_hash,
                    latency_ms,
                    phase="hash_attached",
                    transaction_id=transaction_id,
                    tx_hash=tx_hash,
                    latency_ms=latency_ms,
                    trace_id=trace_id,
                )
                return cast("str", tx_hash)

            sleep(2)

        emit(
            self.logger,
            logging.WARNING,
            "web3.relay_tx.hash_timeout",
            "Timed out waiting for relayer tx hash: tx_id=%s",
            transaction_id,
            phase="timeout",
            success=False,
            transaction_id=transaction_id,
            trace_id=trace_id,
        )
        return None

    def _execute_calls(
        self,
        calls: list[dict[str, Any]],
        operation_name: str,
        metadata: str | None = None,
    ) -> list[TransactionReceipt]:
        """Execute a batch of calls through the gasless relay."""
        match self.signature_type:
            case 1:
                proxy_txns = [
                    {
                        "typeCode": 1,
                        "to": call["to"],
                        "value": call.get("value", 0),
                        "data": call["data"],
                    }
                    for call in calls
                ]
                body = self._build_proxy_relay_transactions(
                    proxy_txns, metadata or "batch"
                )
            case 2:
                body = self._build_safe_relay_transaction(
                    self.multisend_address,
                    self._encode_multisend(calls),
                    metadata or "batch",
                    operation=1,
                )
            case 3:
                body = self._build_deposit_relay_transactions(
                    [
                        {
                            "target": call["to"],
                            "value": str(call.get("value", 0)),
                            "data": call["data"],
                        }
                        for call in calls
                    ],
                    metadata or "batch",
                )
            case _:
                msg = f"Invalid signature_type: {self.signature_type}"
                raise ValueError(msg)

        return [
            self._submit_relay_transaction(
                body,
                operation_name,
                current_or_new_trace_id(),
                time(),
                web3_action=_web3_action(operation_name),
            )
        ]

    def _get_relay_nonce(self, wallet_type: Literal["PROXY", "SAFE", "WALLET"]) -> int:
        """Get nonce from relay for Safe wallet."""
        url = f"{self.relay_url}/nonce"
        params = {
            "address": self.get_base_wallet_address(),
            "type": wallet_type,
        }
        response = self.client.get(url, params=params)
        response.raise_for_status()
        return int(response.json()["nonce"])

    def _build_deposit_wallet_calls(
        self, calls: list[DepositWalletCall | dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Normalize Deposit wallet calls into relay payload dicts."""
        normalized_calls: list[dict[str, Any]] = []
        for call in calls:
            if isinstance(call, DepositWalletCall):
                normalized_calls.append(call.to_dict())
                continue

            normalized_calls.append(
                {
                    "target": call["target"],
                    "value": str(call.get("value", "0")),
                    "data": call["data"],
                }
            )
        return normalized_calls

    def _build_deposit_wallet_signature(
        self,
        wallet_address: str,
        nonce: str,
        deadline: str,
        calls: list[dict[str, Any]],
    ) -> str:
        """Build the Deposit wallet batch signature."""
        typed_calls = [
            {
                "target": call["target"],
                "value": int(call.get("value", 0)),
                "data": call["data"],
            }
            for call in calls
        ]

        full_message = {
            "primaryType": "Batch",
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "Call": [
                    {"name": "target", "type": "address"},
                    {"name": "value", "type": "uint256"},
                    {"name": "data", "type": "bytes"},
                ],
                "Batch": [
                    {"name": "wallet", "type": "address"},
                    {"name": "nonce", "type": "uint256"},
                    {"name": "deadline", "type": "uint256"},
                    {"name": "calls", "type": "Call[]"},
                ],
            },
            "domain": {
                "name": DEPOSIT_WALLET_DOMAIN_NAME,
                "version": DEPOSIT_WALLET_DOMAIN_VERSION,
                "chainId": self.chain_id,
                "verifyingContract": wallet_address,
            },
            "message": {
                "wallet": wallet_address,
                "nonce": int(nonce),
                "deadline": int(deadline),
                "calls": typed_calls,
            },
        }
        return self.signer.sign_typed_data(full_message)

    def _build_deposit_relay_transactions(
        self, calls: list[DepositWalletCall | dict[str, Any]], metadata: str
    ) -> dict[str, Any]:
        """Build Deposit wallet relay transaction body for one or more calls."""
        wallet_address = self.get_expected_deposit_wallet()
        wallet_nonce = str(self._get_relay_nonce(wallet_type="WALLET"))
        deadline = str(
            int(time()) + self.DEFAULT_DEPOSIT_WALLET_DEADLINE_SECONDS
        )
        normalized_calls = self._build_deposit_wallet_calls(calls)
        signature = self._build_deposit_wallet_signature(
            wallet_address=str(wallet_address),
            nonce=wallet_nonce,
            deadline=deadline,
            calls=normalized_calls,
        )

        return {
            "from": self.get_base_wallet_address(),
            "metadata": metadata,
            "nonce": wallet_nonce,
            "signature": signature,
            "to": self.deposit_wallet_factory_address,
            "type": "WALLET",
            "depositWalletParams": {
                "depositWallet": wallet_address,
                "deadline": deadline,
                "calls": normalized_calls,
            },
        }

    def _build_deposit_relay_transaction(
        self, to: ChecksumAddress, data: str, metadata: str
    ) -> dict[str, Any]:
        """Build Deposit wallet relay body for a single call."""
        return self._build_deposit_relay_transactions(
            [{"target": to, "value": "0", "data": data}],
            metadata,
        )

    def _build_proxy_relay_transaction(
        self, to: ChecksumAddress, data: str, metadata: str
    ) -> dict[str, Any]:
        """Build Proxy relay transaction body."""
        return self._build_proxy_relay_transactions(
            [{"typeCode": 1, "to": to, "value": 0, "data": data}],
            metadata,
        )

    def _build_proxy_relay_transactions(
        self, proxy_txns: list[dict[str, object]], metadata: str
    ) -> dict[str, Any]:
        """Build Proxy relay transaction body for one or more calls."""
        proxy_nonce = self._get_relay_nonce(wallet_type="PROXY")
        gas_price = "0"
        relayer_fee = "0"

        encoded_txn = self._encode_proxy_calls(proxy_txns)

        try:
            estimation_txn: TxParams = {
                "from": self.get_base_wallet_address(),
                "to": self.proxy_factory_address,
                "data": HexStr(encoded_txn),
            }
            estimated_gas = self.w3.eth.estimate_gas(estimation_txn)
            gas_limit = str(int(estimated_gas * 1.3))
        except TimeExhausted as e:
            self.logger.warning(
                "Timeout during gas estimation for proxy transaction, using default: %s",
                e,
                extra=log_extra(error=str(e)),
            )
            gas_limit = str(10_000_000)

        struct = create_proxy_struct(
            from_address=self.get_base_wallet_address(),
            to=self.proxy_factory_address,
            data=encoded_txn,
            tx_fee=relayer_fee,
            gas_price=gas_price,
            gas_limit=gas_limit,
            nonce=str(proxy_nonce),
            relay_hub_address=self.relay_hub,
            relay_address=self.relay_address,
        )

        struct_hash = "0x" + self.w3.keccak(struct).hex()

        signature = self.account.sign_message(
            encode_defunct(hexstr=struct_hash)
        ).signature.hex()

        return {
            "data": encoded_txn,
            "from": self.get_base_wallet_address(),
            "metadata": metadata,
            "nonce": str(proxy_nonce),
            "proxyWallet": self.get_poly_proxy_wallet_address(),
            "signature": "0x" + signature,
            "signatureParams": {
                "gasPrice": gas_price,
                "gasLimit": gas_limit,
                "relayerFee": relayer_fee,
                "relayHub": self.relay_hub,
                "relay": self.relay_address,
            },
            "to": self.proxy_factory_address,
            "type": "PROXY",
        }

    def _build_safe_relay_transaction(
        self, to: ChecksumAddress, data: str, metadata: str, operation: int = 0
    ) -> dict[str, Any]:
        """Build Safe relay transaction body."""
        safe_nonce = self._get_relay_nonce(wallet_type="SAFE")

        safe_txn: SafeTxn = {
            "to": to,
            "data": data,
            "operation": operation,
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
            "from": self.get_base_wallet_address(),
            "metadata": metadata,
            "nonce": str(safe_nonce),
            "proxyWallet": self.get_safe_proxy_wallet_address(),
            "signature": "0x" + signature,
            "signatureParams": {
                "baseGas": "0",
                "gasPrice": "0",
                "gasToken": ADDRESS_ZERO,
                "operation": str(operation),
                "refundReceiver": ADDRESS_ZERO,
                "safeTxnGas": "0",
            },
            "to": to,
            "type": "SAFE",
        }

    def _build_safe_create_relay_transaction(self) -> dict[str, Any]:
        """Build Safe deployment relay transaction body."""
        signature = create_safe_create_signature(
            account=self.account, chain_id=self.chain_id
        )

        match signature[-2:]:
            case "00" | "1b":
                signature = signature[:-2] + "1f"
            case "01" | "1c":
                signature = signature[:-2] + "20"

        return {
            "data": "0x",
            "from": self.get_base_wallet_address(),
            "metadata": "safe-create",
            "nonce": str(self._get_relay_nonce(wallet_type="SAFE")),
            "proxyWallet": self.get_safe_proxy_wallet_address(),
            "signature": "0x" + signature,
            "signatureParams": {
                "baseGas": "0",
                "gasPrice": "0",
                "gasToken": ADDRESS_ZERO,
                "operation": "0",
                "refundReceiver": ADDRESS_ZERO,
                "safeTxnGas": "0",
            },
            "to": ADDRESS_ZERO,
            "type": "SAFE",
        }

    def deploy_safe_wallet(self) -> TransactionReceipt:
        """Deploy a Safe wallet via gasless relay."""
        body = self._build_safe_create_relay_transaction()
        return self._submit_relay_transaction(
            body,
            "Safe Deployment",
            current_or_new_trace_id(),
            time(),
            web3_action="DEPLOY_SAFE",
        )
