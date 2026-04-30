from typing import Literal

# Access levels
L0 = 0
L1 = 1
L2 = 2


CREDENTIAL_CREATION_WARNING = """🚨🚨🚨
Your credentials CANNOT be recovered after they've been created.
Be sure to store them safely!
🚨🚨🚨"""


L1_AUTH_UNAVAILABLE = "A private key is needed to interact with this endpoint!"

L2_AUTH_UNAVAILABLE = "API Credentials are needed to interact with this endpoint!"

ADDRESS_ZERO = "0x0000000000000000000000000000000000000000"
BYTES32_ZERO = "0x0000000000000000000000000000000000000000000000000000000000000000"
HASH_ZERO = BYTES32_ZERO
ORDER_VERSION_MISMATCH_ERROR = "order_version_mismatch"

AMOY: Literal[80002] = 80002
POLYGON: Literal[137] = 137
END_CURSOR = "LTE="

BUY = "BUY"
SELL = "SELL"
