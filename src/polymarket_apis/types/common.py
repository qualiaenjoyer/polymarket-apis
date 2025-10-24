import re
from datetime import UTC, datetime
from typing import Annotated

from dateutil import parser
from pydantic import AfterValidator, BaseModel, BeforeValidator, Field


def validate_keccak256(v: str) -> str:
    if not re.match(r"^0x[a-fA-F0-9]{64}$", v):
        msg = "Invalid Keccak256 hash format"
        raise ValueError(msg)
    return v


def parse_flexible_datetime(v: str | datetime) -> datetime:
    """Parse datetime from multiple formats using dateutil."""
    if v in {"NOW*()", "NOW()"}:
        return datetime.fromtimestamp(0, tz=UTC)

    if isinstance(v, str):
        return parser.parse(v)
    return v


FlexibleDatetime = Annotated[datetime, BeforeValidator(parse_flexible_datetime)]
EthAddress = Annotated[str, Field(pattern=r"^0x[A-Fa-f0-9]{40}$")]
Keccak256 = Annotated[str, AfterValidator(validate_keccak256)]
EmptyString = Annotated[str, Field(pattern=r"^$", description="An empty string")]


class TimeseriesPoint(BaseModel):
    value: float
    timestamp: datetime
