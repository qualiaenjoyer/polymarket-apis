from datetime import datetime
from typing import Annotated
import re

from pydantic import BeforeValidator, Field, AfterValidator


def validate_keccak256(v: str) -> str:
    if not re.match(r"^0x[a-fA-F0-9]{64}$", v):
        raise ValueError("Invalid Keccak256 hash format")
    return v

def parse_timestamp(v: str) -> datetime:
    if isinstance(v, str):
        # Handle the timezone offset by padding it to 4 digits
        return datetime.strptime(v + "00", "%Y-%m-%d %H:%M:%S.%f%z")


TimestampWithTZ = Annotated[datetime, BeforeValidator(parse_timestamp)]
EthAddress = Annotated[str, Field(pattern=r"^0x[A-Fa-f0-9]{40}$")]
Keccak256 = Annotated[str, AfterValidator(validate_keccak256)]
EmptyString = Annotated[str, Field(pattern=r"^$", description="An empty string")]
