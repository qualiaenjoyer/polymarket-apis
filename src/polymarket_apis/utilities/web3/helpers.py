import re
from collections.abc import Iterable
from typing import Any, Literal, NotRequired, TypedDict, cast

from eth_abi.abi import encode
from eth_account import Account
from eth_account.datastructures import SignedMessage
from eth_account.messages import encode_defunct
from eth_typing import ChecksumAddress
from eth_utils.address import to_checksum_address
from eth_utils.conversions import to_bytes
from eth_utils.crypto import keccak
from web3.constants import ADDRESS_ZERO
from web3.contract import Contract

from ...types.common import EthAddress
from ..web3 import constants


def get_market_index(question_id: str) -> int:
    """Extract the market index from a question ID (last 2 hex characters)."""
    return int(question_id[-2:], 16)


def get_index_set(question_ids: list[str]) -> int:
    """Calculate bitwise index set from question IDs."""
    indices = [get_market_index(question_id) for question_id in question_ids]
    return sum(1 << index for index in set(indices))


def detect_wallet_signature_type(
    address: EthAddress,
    rpc_url: str = "https://tenderly.rpc.polygon.community",
) -> Literal[0, 1, 2, 3] | None:
    """Detect the signature type for a wallet address from runtime code."""
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    code = (
        w3.eth.get_code(w3.to_checksum_address(address))
        .hex()
        .removeprefix("0x")
        .lower()
    )
    signature_type = get_signature_type_from_runtime_code(code)
    if signature_type is None:
        msg = (
            f"Could not auto-detect signature_type for funder address {address}. "
            "The address has an unknown contract runtime; provide signature_type explicitly."
        )
        raise ValueError(msg)
    return signature_type


INT_REGEX = re.compile(r"^u?int(\d*)$")
BYTES_REGEX = re.compile(r"^bytes(\d+)$")


def _pack_primitive(typ: str, val: Any) -> bytes:
    if isinstance(val, str) and val.startswith("0x"):
        raw = bytes.fromhex(val[2:])
    elif isinstance(val, bytes):
        raw = val
    else:
        raw = val

    if typ == "string":
        if not isinstance(raw, bytes | str):
            msg = "string value must be str or bytes"
            raise TypeError(msg)
        return raw.encode() if isinstance(raw, str) else raw
    if typ == "bytes":
        if isinstance(raw, int):
            msg = "bytes value must be hex/bytes/str"
            raise TypeError(msg)
        if isinstance(raw, str):
            return raw.encode()
        return raw

    m = BYTES_REGEX.match(typ)
    if m:
        n = int(m.group(1))
        if isinstance(raw, int):
            b = raw.to_bytes(n, "big")
        elif isinstance(raw, str) and raw.startswith("0x"):
            b = bytes.fromhex(raw[2:])
        elif isinstance(raw, bytes | bytearray):
            b = bytes(raw)
        else:
            msg = f"unsupported value for {typ}"
            raise TypeError(msg)
        if len(b) != n:
            if len(b) > n:
                return b[:n]
            return b.ljust(n, b"\x00")
        return b

    if typ == "address":
        if isinstance(raw, str) and raw.startswith("0x"):
            addr = raw[2:]
        elif isinstance(raw, str):
            addr = raw
        elif isinstance(raw, bytes | bytearray):
            return bytes(raw[-20:])
        else:
            msg = "address must be hex string or bytes"
            raise TypeError(msg)
        addr = addr.rjust(40, "0")[-40:]
        return bytes.fromhex(addr)

    m = INT_REGEX.match(typ)
    if m:
        bits = int(m.group(1)) if m.group(1) else 256
        size = bits // 8
        if isinstance(raw, bytes | bytearray):
            intval = int.from_bytes(raw, "big")
        elif isinstance(raw, str) and raw.startswith("0x"):
            intval = int(raw, 16)
        elif isinstance(raw, int):
            intval = raw
        else:
            msg = f"unsupported value for {typ}"
            raise TypeError(msg)
        if intval < 0:
            intval &= (1 << bits) - 1
        return intval.to_bytes(size, "big")

    msg = f"unsupported type {typ}"
    raise ValueError(msg)


class AbiPackedParam(TypedDict):
    type: str
    value: Any


def abi_encode_packed(*params: AbiPackedParam) -> bytes:
    """
    Takes in sequence of {'type': str, 'value': any}.

    returns: concatenated packed bytes (no 0x prefix).
    """
    parts: list[bytes] = []
    for p in params:
        typ = p["type"]
        val = p["value"]
        if typ.endswith("[]"):
            inner = typ[:-2]
            if not isinstance(val, Iterable):
                msg = f"expected array value for {typ}"
                raise TypeError(msg)
            for elem in val:
                parts.append(abi_encode_packed({"type": inner, "value": elem}))
            continue
        parts.append(_pack_primitive(typ, val))
    return b"".join(parts)


def split_signature(signature_hex: str) -> dict[str, Any]:
    """
    Split a signature into r, s, v components compatible with Safe factory.

    Args:
        signature_hex: Signature as hex string

    Returns:
        dict: Dictionary with r, s, v components properly formatted for the contract

    """
    # Remove 0x prefix if present
    signature_hex = signature_hex.removeprefix("0x")

    # Convert to bytes
    signature_bytes = bytes.fromhex(signature_hex)

    if len(signature_bytes) != 65:
        msg = "Invalid signature length"
        raise ValueError(msg)

    # Extract r, s, v
    r = signature_bytes[:32]
    s = signature_bytes[32:64]
    v = signature_bytes[64]

    if v < 27:
        if v in {0, 1}:
            v += 27
        else:
            msg = "Invalid signature v value"
            raise ValueError(msg)

    # Return properly formatted components for the contract:
    # - r and s as bytes32 (keep as bytes, web3.py will handle conversion)
    # - v as uint8 (integer)
    return {
        "r": r,  # bytes32
        "s": s,  # bytes32
        "v": v,  # uint8
    }


def create_safe_create_signature(
    account: Account, chain_id: Literal[137, 80002]
) -> str:
    """
    Create EIP-712 signature for Safe creation.

    Returns:
        str: The signature as hex string

    """
    # EIP-712 domain
    domain = {
        "name": "Polymarket Contract Proxy Factory",
        "chainId": chain_id,
        "verifyingContract": "0xaacFeEa03eb1561C4e67d661e40682Bd20E3541b",
    }

    # EIP-712 types
    types = {
        "CreateProxy": [
            {"name": "paymentToken", "type": "address"},
            {"name": "payment", "type": "uint256"},
            {"name": "paymentReceiver", "type": "address"},
        ]
    }

    # Values to sign
    values = {
        "paymentToken": ADDRESS_ZERO,
        "payment": 0,
        "paymentReceiver": ADDRESS_ZERO,
    }

    # Create the signature using eth_account
    signature: SignedMessage = account.sign_typed_data(domain, types, values)

    return signature.signature.hex()


ERC1967_CONST1 = "0xcc3735a920a3ca505d382bbc545af43d6000803e6038573d6000fd5b3d6000f3"
ERC1967_CONST2 = "0x5155f3363d3d373d3d363d7f360894a13ba1a3210667c828492db98dca3e2076"
ERC1967_PREFIX = 0x61003D3D8160233D3973


def get_create2_address(
    bytecode_hash: str, from_address: str, salt: bytes
) -> ChecksumAddress:
    """Derive a CREATE2 address from init code hash, factory, and salt."""
    payload = (
        b"\xff"
        + to_bytes(hexstr=from_address)
        + salt
        + to_bytes(hexstr=bytecode_hash)
    )
    return to_checksum_address("0x" + keccak(payload)[12:].hex())


def init_code_hash_erc1967(implementation: str, args: bytes) -> str:
    """Build the init code hash used by the deposit-wallet ERC1967 proxy."""
    implementation = to_checksum_address(implementation)
    n = len(args)
    combined = ERC1967_PREFIX + (n << 56)
    init_code = (
        combined.to_bytes(10, "big")
        + to_bytes(hexstr=implementation)
        + to_bytes(hexstr="0x6009")
        + to_bytes(hexstr=ERC1967_CONST2)
        + to_bytes(hexstr=ERC1967_CONST1)
        + args
    )
    return "0x" + keccak(init_code).hex()


def derive_deposit_wallet(owner: str, factory: str, implementation: str) -> ChecksumAddress:
    """Derive the expected deposit-wallet address from the controlling EOA."""
    owner = to_checksum_address(owner)
    factory = to_checksum_address(factory)
    implementation = to_checksum_address(implementation)

    wallet_id = to_bytes(hexstr=owner).rjust(32, b"\x00")
    args = encode(["address", "bytes32"], [factory, wallet_id])
    salt = keccak(args)
    bytecode_hash = init_code_hash_erc1967(implementation, args)
    wallet_address = get_create2_address(
        bytecode_hash=bytecode_hash,
        from_address=factory,
        salt=salt,
    )
    return wallet_address


class SafeTxn(TypedDict):
    to: ChecksumAddress
    value: int
    data: str
    operation: NotRequired[int]


def sign_safe_transaction(
    account: Account, safe: Contract, safe_txn: SafeTxn, nonce: int
) -> SignedMessage:
    safe_tx_gas = 0
    base_gas = 0
    gas_price = 0
    gas_token = ADDRESS_ZERO
    refund_receiver = ADDRESS_ZERO

    tx_hash_bytes = safe.functions.getTransactionHash(
        safe_txn["to"],
        safe_txn["value"],
        safe_txn["data"],
        safe_txn.get("operation", 0),
        safe_tx_gas,
        base_gas,
        gas_price,
        gas_token,
        refund_receiver,
        nonce,
    ).call()

    tx_hash_hex = tx_hash_bytes.hex()
    message = encode_defunct(hexstr=tx_hash_hex)
    return cast("SignedMessage", account.sign_message(message))


def get_packed_signature(signed: SignedMessage) -> bytes:
    r = signed.r
    s = signed.s
    v = signed.v

    match v:
        case 0 | 1:
            v += 31
        case 27 | 28:
            v += 4
        case _:
            msg = "Invalid signature V value"
            raise ValueError(msg)

    packed_sig = abi_encode_packed(
        {"type": "uint256", "value": r},
        {"type": "uint256", "value": s},
        {"type": "uint8", "value": v},
    )

    return packed_sig


def create_proxy_struct(
    from_address: str,
    to: str,
    data: str,
    tx_fee: str,
    gas_price: str,
    gas_limit: str,
    nonce: str,
    relay_hub_address: str,
    relay_address: str,
) -> bytes:
    """Create struct hash for proxy wallet signature."""
    relay_hub_prefix = b"rlx:"

    encoded_from = bytes.fromhex(from_address[2:])
    encoded_to = bytes.fromhex(to[2:])
    encoded_data = bytes.fromhex(data.removeprefix("0x"))
    encoded_tx_fee = int(tx_fee).to_bytes(32, byteorder="big")
    encoded_gas_price = int(gas_price).to_bytes(32, byteorder="big")
    encoded_gas_limit = int(gas_limit).to_bytes(32, byteorder="big")
    encoded_nonce = int(nonce).to_bytes(32, byteorder="big")
    encoded_relay_hub = bytes.fromhex(relay_hub_address[2:])
    encoded_relay = bytes.fromhex(relay_address[2:])

    struct = (
        relay_hub_prefix
        + encoded_from
        + encoded_to
        + encoded_data
        + encoded_tx_fee
        + encoded_gas_price
        + encoded_gas_limit
        + encoded_nonce
        + encoded_relay_hub
        + encoded_relay
    )

    return struct


def get_signature_type_from_runtime_code(code: str) -> Literal[0, 1, 2, 3] | None:
    match code:
        case "":
            return 0
        case constants.POLY_PROXY_RUNTIME_CODE:
            return 1
        case constants.SAFE_PROXY_RUNTIME_CODE:
            return 2
        case _ if code.startswith(constants.DEPOSIT_RUNTIME_CODE):
            return 3
        case _:
            return None
