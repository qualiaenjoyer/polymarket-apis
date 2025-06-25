import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field


def validate_keccak256(v: str) -> str:
    if not re.match(r"^0x[a-fA-F0-9]{64}$", v):
        msg = "Invalid Keccak256 hash format"
        raise ValueError(msg)
    return v

def parse_timestamp(v: str) -> datetime:
    # Normalize '+00' to '+0000' for timezone
    if v.endswith("+00"):
        v = v[:-3] + "+0000"

    # Pad fractional seconds to 6 digits if present
    if "." in v:
        dot_pos = v.find(".")
        tz_pos = v.find("+", dot_pos)  # Find timezone start after '.'
        if tz_pos == -1:
            tz_pos = v.find("-", dot_pos)

        if tz_pos != -1:
            frac = v[dot_pos+1:tz_pos]
            if len(frac) < 6:
                frac = frac.ljust(6, "0")
                v = f"{v[:dot_pos+1]}{frac}{v[tz_pos:]}"

    # Try parsing with and without microseconds
    for fmt in ("%Y-%m-%d %H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S%z"):
        try:
            return datetime.strptime(v, fmt) # noqa: DTZ007
        except ValueError:
            continue
    msg = f"Time data '{v}' does not match expected formats."
    raise ValueError(msg)


TimestampWithTZ = Annotated[datetime, BeforeValidator(parse_timestamp)]
EthAddress = Annotated[str, Field(pattern=r"^0x[A-Fa-f0-9]{40}$")]
Keccak256 = Annotated[str, AfterValidator(validate_keccak256)]
EmptyString = Annotated[str, Field(pattern=r"^$", description="An empty string")]

class TimeseriesPoint(BaseModel):
    t: datetime
    p: float
