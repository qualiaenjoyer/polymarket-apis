from typing import Annotated
from pydantic import Field, BeforeValidator
from datetime import datetime


def parse_timestamp(v: str) -> datetime:
    if isinstance(v, str):
        # Handle the timezone offset by padding it to 4 digits
        if v.endswith("+00"):
            v = v.replace("+00", "+0000")
        return datetime.strptime(v, "%Y-%m-%d %H:%M:%S.%f%z")
    return v


TimestampWithTZ = Annotated[datetime, BeforeValidator(parse_timestamp)]
EthAddress = Annotated[str, Field(pattern=r"^0x[A-Fa-f0-9]{40}$")]
Keccak256 = Annotated[
    str,
    Field(
        pattern=r"^0x[a-fA-F0-9]{64}$",  # Matches a 64-character hexadecimal string
        description="A Keccak-256 hash (64-character hexadecimal string)",
    ),
]
