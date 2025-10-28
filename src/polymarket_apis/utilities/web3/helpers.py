import re
from collections.abc import Iterable
from typing import Any

from eth_account import Account
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


def sign_safe_transaction(
    account: Account, safe: Contract, safe_txn: dict, nonce: int
) -> bytes:
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
    signed = account.sign_message(message)
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
