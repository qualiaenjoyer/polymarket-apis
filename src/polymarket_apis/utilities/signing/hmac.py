import base64
import hashlib
import hmac


def build_hmac_signature(
    secret: str,
    timestamp: str,
    method: str,
    request_path: str,
    body=None,
):
    """Creates an HMAC signature by signing a payload with the secret."""
    base64_secret = base64.urlsafe_b64decode(secret)
    message = str(timestamp) + str(method) + str(request_path)
    if body:
        # NOTE: Necessary to replace single quotes with double quotes
        # to generate the same hmac message as go and typescript
        message += str(body).replace("'", '"')

    h = hmac.new(base64_secret, bytes(message, "utf-8"), hashlib.sha256)

    # ensure base64 encoded
    return (base64.urlsafe_b64encode(h.digest())).decode("utf-8")
