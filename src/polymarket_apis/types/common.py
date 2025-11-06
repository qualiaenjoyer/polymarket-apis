import re
from datetime import UTC, datetime
from typing import Annotated, Any

from dateutil import parser
from hexbytes import HexBytes
from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field


def parse_flexible_datetime(v: str | datetime) -> datetime:
    """Parse datetime from multiple formats using dateutil."""
    if v in {"NOW*()", "NOW()"}:
        return datetime.fromtimestamp(0, tz=UTC)

    if isinstance(v, str):
        parsed = parser.parse(v)
        if not isinstance(parsed, datetime):
            msg = f"Failed to parse '{v}' as datetime, got {type(parsed)}"
            raise TypeError(msg)
        return parsed
    return v


def validate_keccak256(v: str | HexBytes | bytes) -> str:
    """Validate and normalize Keccak256 hash format."""
    # Convert HexBytes/bytes to string
    if isinstance(v, (HexBytes, bytes)):
        v = v.hex()

    # Ensure string and add 0x prefix if missing
    if not isinstance(v, str):
        msg = f"Expected string or bytes, got {type(v)}"
        raise TypeError(msg)

    if not v.startswith("0x"):
        v = "0x" + v

    # Validate format: 0x followed by 64 hex characters
    if not re.match(r"^0x[a-fA-F0-9]{64}$", v):
        msg = f"Invalid Keccak256 hash format: {v}"
        raise ValueError(msg)

    return v


def validate_eth_address(v: str | HexBytes | bytes) -> str:
    """Validate and normalize Ethereum address format."""
    # Convert HexBytes/bytes to string
    if isinstance(v, (HexBytes, bytes)):
        v = v.hex()

    # Ensure string and add 0x prefix if missing
    if not isinstance(v, str):
        msg = f"Expected string or bytes, got {type(v)}"
        raise TypeError(msg)

    if not v.startswith("0x"):
        v = "0x" + v

    # Validate format: 0x followed by 40 hex characters
    if not re.match(r"^0x[a-fA-F0-9]{40}$", v, re.IGNORECASE):
        msg = f"Invalid Ethereum address format: {v}"
        raise ValueError(msg)

    return v


def hexbytes_to_str(v: Any) -> str:
    """Convert HexBytes to hex string with 0x prefix."""
    if isinstance(v, HexBytes):
        hex_str = v.hex()
        return hex_str if hex_str.startswith("0x") else f"0x{hex_str}"
    if isinstance(v, bytes):
        return "0x" + v.hex()
    if isinstance(v, str) and not v.startswith("0x"):
        return f"0x{v}"
    return v


def validate_keccak_or_padded(v: Any) -> str:
    """
    Validate Keccak256 or accept padded addresses (32 bytes with leading zeros).

    Some log topics are padded addresses, not proper Keccak256 hashes.
    """
    # First convert HexBytes/bytes to string with 0x prefix
    if isinstance(v, (HexBytes, bytes)):
        v = v.hex()

    # Ensure it's a string
    if not isinstance(v, str):
        msg = f"Expected string or bytes, got {type(v)}"
        raise TypeError(msg)

    # Add 0x prefix if missing
    if not v.startswith("0x"):
        v = "0x" + v

    # Accept 66 character hex strings (0x + 64 hex chars)
    if len(v) == 66 and all(c in "0123456789abcdefABCDEF" for c in v[2:]):
        return v

    msg = (
        f"Invalid hash format: expected 66 characters (0x + 64 hex), got {len(v)}: {v}"
    )
    raise ValueError(msg)


FlexibleDatetime = Annotated[datetime, BeforeValidator(parse_flexible_datetime)]
EthAddress = Annotated[str, AfterValidator(validate_eth_address)]
Keccak256 = Annotated[str, AfterValidator(validate_keccak256)]
HexString = Annotated[str, BeforeValidator(hexbytes_to_str)]
Keccak256OrPadded = Annotated[str, BeforeValidator(validate_keccak_or_padded)]
EmptyString = Annotated[str, Field(pattern=r"^$", description="An empty string")]


class TimeseriesPoint(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    value: float = Field(alias="p")
    timestamp: datetime = Field(alias="t")
