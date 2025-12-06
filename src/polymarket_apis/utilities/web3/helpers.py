import re
from collections.abc import Iterable
from typing import Any, Literal

from eth_account import Account
from eth_account.datastructures import SignedMessage
from eth_account.messages import encode_defunct
from web3.constants import ADDRESS_ZERO
from web3.contract import Contract


def get_market_index(question_id: str) -> int:
    """Extract the market index from a question ID (last 2 hex characters)."""
    return int(question_id[-2:], 16)


def get_index_set(question_ids: list[str]) -> int:
    """Calculate bitwise index set from question IDs."""
    indices = [get_market_index(question_id) for question_id in question_ids]
    return sum(1 << index for index in set(indices))


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

    m = re.match(r"^bytes(\d+)$", typ)
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

    m = re.match(r"^u?int(\d*)$", typ)
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


def abi_encode_packed(*params: dict) -> bytes:
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
    signature = account.sign_typed_data(domain, types, values)

    return signature.signature.hex()


def sign_safe_transaction(
    account: Account, safe: Contract, safe_txn: dict, nonce: int
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
    return account.sign_message(message)


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
