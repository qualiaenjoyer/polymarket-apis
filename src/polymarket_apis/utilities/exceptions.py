class InvalidPriceError(Exception):
    pass


class InvalidTickSizeError(Exception):
    pass


class InvalidFeeRateError(Exception):
    pass


class LiquidityError(Exception):
    pass


class MissingOrderbookError(Exception):
    pass


class SafeAlreadyDeployedError(Exception):
    """Raised when attempting to deploy a Safe that has already been deployed."""


class BuilderRateLimitError(Exception):
    """Shared builder credentials have hit their rate limit."""

