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

class AuthenticationRequiredError(ValueError):
    """Raised when authentication credentials are required but not provided."""
