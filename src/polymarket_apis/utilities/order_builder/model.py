import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Optional, TypedDict, cast

from eth_abi.abi import encode as abi_encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_typing import HexStr
from eth_utils.address import to_checksum_address
from eth_utils.crypto import keccak
from poly_eip712_structs import Address, Bytes, EIP712Struct, Uint, make_domain

from ..constants import BYTES32_ZERO
from ..signing.signer import Signer

CTF_EXCHANGE_V2_DOMAIN_NAME = "Polymarket CTF Exchange"
CTF_EXCHANGE_V2_DOMAIN_VERSION = "2"
CTF_EXCHANGE_V2_ORDER_STRUCT = [
    {"name": "salt", "type": "uint256"},
    {"name": "maker", "type": "address"},
    {"name": "signer", "type": "address"},
    {"name": "tokenId", "type": "uint256"},
    {"name": "makerAmount", "type": "uint256"},
    {"name": "takerAmount", "type": "uint256"},
    {"name": "side", "type": "uint8"},
    {"name": "signatureType", "type": "uint8"},
    {"name": "timestamp", "type": "uint256"},
    {"name": "metadata", "type": "bytes32"},
    {"name": "builder", "type": "bytes32"},
]
EIP712_DOMAIN = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
    {"name": "verifyingContract", "type": "address"},
]

EOA = 0
POLY_PROXY = 1
POLY_GNOSIS_SAFE = 2
POLY_1271 = 3

ORDER_TYPE_STRING = (
    "Order(uint256 salt,address maker,address signer,uint256 tokenId,"
    "uint256 makerAmount,uint256 takerAmount,uint8 side,uint8 signatureType,"
    "uint256 timestamp,bytes32 metadata,bytes32 builder)"
)
SOLADY_TYPE_STRING = (
    "TypedDataSign(Order contents,string name,string version,uint256 chainId,"
    "address verifyingContract,bytes32 salt)"
    f"{ORDER_TYPE_STRING}"
)
DOMAIN_TYPE_STRING = (
    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
)

ORDER_TYPE_HASH = keccak(text=ORDER_TYPE_STRING)
DOMAIN_TYPE_HASH = keccak(text=DOMAIN_TYPE_STRING)
SOLADY_TYPE_HASH = keccak(text=SOLADY_TYPE_STRING)
DEPOSIT_WALLET_NAME_HASH = keccak(text="DepositWallet")
DEPOSIT_WALLET_VERSION_HASH = keccak(text="1")
CTF_EXCHANGE_NAME_HASH = keccak(text=CTF_EXCHANGE_V2_DOMAIN_NAME)
CTF_EXCHANGE_VERSION_HASH = keccak(text=CTF_EXCHANGE_V2_DOMAIN_VERSION)
DEPOSIT_WALLET_DOMAIN_SALT = bytes.fromhex(BYTES32_ZERO.replace("0x", "").zfill(64))

BUY_SIDE: Literal[0] = 0
SELL_SIDE: Literal[1] = 1


def generate_seed() -> int:
    return int(random.random() * (time.time_ns() // 1_000_000))


def prepend_zx(value: str) -> str:
    return value if value.startswith("0x") else f"0x{value}"


def _hex_to_bytes32(hex_str: str) -> bytes:
    return bytes.fromhex(hex_str.replace("0x", "").zfill(64))


class Order(EIP712Struct):  # type: ignore[misc]
    salt = Uint(256)
    maker = Address()
    signer = Address()
    tokenId = Uint(256)  # noqa: N815
    makerAmount = Uint(256)  # noqa: N815
    takerAmount = Uint(256)  # noqa: N815
    side = Uint(8)
    signatureType = Uint(8)  # noqa: N815
    timestamp = Uint(256)
    metadata = Bytes(32)
    builder = Bytes(32)


@dataclass
class OrderData:
    maker: str
    token_id: str
    maker_amount: str
    taker_amount: str
    side: int
    signer: Optional[str] = None
    signature_type: Optional[int] = None
    timestamp: Optional[str] = None
    metadata: Optional[str] = None
    builder: Optional[str] = None
    expiration: Optional[str] = None


class OrderTypedDataMessage(TypedDict):
    salt: int
    maker: str
    signer: str
    tokenId: int
    makerAmount: int
    takerAmount: int
    side: int
    signatureType: int
    timestamp: int
    metadata: bytes
    builder: bytes


class OrderTypedData(TypedDict):
    primaryType: str
    types: dict[str, Any]
    domain: dict[str, Any]
    message: OrderTypedDataMessage


@dataclass
class SignedOrder:
    salt: str
    maker: str
    signer: str
    token_id: str
    maker_amount: str
    taker_amount: str
    side: int
    signature_type: int
    timestamp: str
    metadata: str
    builder: str
    expiration: str = "0"
    signature: str = ""

    def dict(self) -> dict[str, str | int]:
        return {
            "salt": int(self.salt),
            "maker": self.maker,
            "signer": self.signer,
            "tokenId": self.token_id,
            "makerAmount": self.maker_amount,
            "takerAmount": self.taker_amount,
            "side": "BUY" if self.side == BUY_SIDE else "SELL",
            "expiration": self.expiration,
            "signatureType": int(self.signature_type),
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "builder": self.builder,
            "signature": self.signature,
        }


class OrderBuilder:
    def __init__(
        self,
        exchange_address: str,
        chain_id: int,
        signer: Signer,
        salt_generator: Callable[[], int] = generate_seed,
    ) -> None:
        self.contract_address = to_checksum_address(exchange_address)
        self.chain_id = chain_id
        self.signer = signer
        self.salt_generator = salt_generator
        self.app_domain_separator = keccak(
            abi_encode(
                ["bytes32", "bytes32", "bytes32", "uint256", "address"],
                [
                    DOMAIN_TYPE_HASH,
                    CTF_EXCHANGE_NAME_HASH,
                    CTF_EXCHANGE_VERSION_HASH,
                    chain_id,
                    self.contract_address,
                ],
            )
        )
        self.domain_separator = make_domain(
            name=CTF_EXCHANGE_V2_DOMAIN_NAME,
            version=CTF_EXCHANGE_V2_DOMAIN_VERSION,
            chainId=str(chain_id),
            verifyingContract=self.contract_address,
        )

    def build_order(self, data: OrderData) -> SignedOrder:
        self._validate_inputs(data)

        signer = data.signer or data.maker
        if (
            data.signature_type != POLY_1271
            and to_checksum_address(signer) != self.signer.address()
        ):
            msg = "Signer does not match"
            raise ValueError(msg)

        timestamp = data.timestamp
        if timestamp is None:
            msg = "timestamp must not be None"
            raise ValueError(msg)

        metadata = data.metadata or BYTES32_ZERO
        builder = data.builder or BYTES32_ZERO
        signature_type = data.signature_type if data.signature_type is not None else EOA

        order = SignedOrder(
            salt=str(self.salt_generator()),
            maker=to_checksum_address(data.maker),
            signer=to_checksum_address(signer),
            token_id=data.token_id,
            maker_amount=data.maker_amount,
            taker_amount=data.taker_amount,
            side=int(data.side),
            signature_type=int(signature_type),
            timestamp=timestamp,
            metadata=metadata,
            builder=builder,
            expiration=data.expiration or "0",
        )
        order.signature = self.build_order_signature(order)
        return order

    def build_order_signature(self, order: SignedOrder) -> str:
        if order.signature_type == POLY_1271:
            return self._build_poly_1271_order_signature(order)

        encoded = encode_typed_data(
            full_message=cast("dict[str, Any]", self.build_order_typed_data(order))
        )
        signed = Account.sign_message(encoded, private_key=self.signer.private_key)
        return cast("str", "0x" + signed.signature.hex())

    def _build_poly_1271_order_signature(self, order: SignedOrder) -> str:
        message = self.build_order_typed_data(order)["message"]
        contents_hash = keccak(
            primitive=abi_encode(
                [
                    "bytes32",
                    "uint256",
                    "address",
                    "address",
                    "uint256",
                    "uint256",
                    "uint256",
                    "uint8",
                    "uint8",
                    "uint256",
                    "bytes32",
                    "bytes32",
                ],
                [
                    ORDER_TYPE_HASH,
                    int(message["salt"]),
                    message["maker"],
                    message["signer"],
                    int(message["tokenId"]),
                    int(message["makerAmount"]),
                    int(message["takerAmount"]),
                    int(message["side"]),
                    int(message["signatureType"]),
                    int(message["timestamp"]),
                    message["metadata"],
                    message["builder"],
                ],
            )
        )
        typed_data_sign_struct_hash = keccak(
            primitive=abi_encode(
                [
                    "bytes32",
                    "bytes32",
                    "bytes32",
                    "bytes32",
                    "uint256",
                    "address",
                    "bytes32",
                ],
                [
                    SOLADY_TYPE_HASH,
                    contents_hash,
                    DEPOSIT_WALLET_NAME_HASH,
                    DEPOSIT_WALLET_VERSION_HASH,
                    self.chain_id,
                    message["signer"],
                    DEPOSIT_WALLET_DOMAIN_SALT,
                ],
            )
        )
        digest = keccak(
            primitive=b"\x19\x01"
            + self.app_domain_separator
            + typed_data_sign_struct_hash
        )
        signed = Account.unsafe_sign_hash(digest, self.signer.private_key)
        inner_signature = signed.signature.hex()
        inner_signature = inner_signature.removeprefix("0x")

        contents_type = ORDER_TYPE_STRING.encode("utf-8").hex()
        contents_type_len = len(ORDER_TYPE_STRING).to_bytes(2, "big").hex()

        return cast(
            "str",
            "0x"
            + inner_signature
            + self.app_domain_separator.hex()
            + contents_hash.hex()
            + contents_type
            + contents_type_len
        )

    def build_signed_order(self, data: OrderData) -> SignedOrder:
        return self.build_order(data)

    def build_order_typed_data(self, order: SignedOrder) -> OrderTypedData:
        return {
            "primaryType": "Order",
            "types": {
                "EIP712Domain": EIP712_DOMAIN,
                "Order": CTF_EXCHANGE_V2_ORDER_STRUCT,
            },
            "domain": {
                "name": CTF_EXCHANGE_V2_DOMAIN_NAME,
                "version": CTF_EXCHANGE_V2_DOMAIN_VERSION,
                "chainId": self.chain_id,
                "verifyingContract": self.contract_address,
            },
            "message": {
                "salt": int(order.salt),
                "maker": order.maker,
                "signer": order.signer,
                "tokenId": int(order.token_id),
                "makerAmount": int(order.maker_amount),
                "takerAmount": int(order.taker_amount),
                "side": int(order.side),
                "signatureType": int(order.signature_type),
                "timestamp": int(order.timestamp),
                "metadata": _hex_to_bytes32(order.metadata),
                "builder": _hex_to_bytes32(order.builder),
            },
        }

    def _create_struct_hash(self, order: Order) -> HexStr:
        struct_hash = prepend_zx(
            keccak(order.signable_bytes(domain=self.domain_separator)).hex()
        )
        return cast("HexStr", struct_hash)

    def _validate_inputs(self, data: OrderData) -> None:
        if (
            data.maker is None
            or data.token_id is None
            or data.maker_amount is None
            or data.taker_amount is None
            or data.side not in [BUY_SIDE, SELL_SIDE]
            or data.signature_type
            not in [None, EOA, POLY_PROXY, POLY_GNOSIS_SAFE, POLY_1271]
        ):
            msg = "Invalid order inputs"
            raise ValueError(msg)

        for name, value in {
            "token_id": data.token_id,
            "maker_amount": data.maker_amount,
            "taker_amount": data.taker_amount,
            "expiration": data.expiration or "0",
            "timestamp": data.timestamp or "0",
        }.items():
            if not value.isnumeric() or int(value) < 0:
                msg = f"{name} must be a non-negative integer string"
                raise ValueError(msg)
