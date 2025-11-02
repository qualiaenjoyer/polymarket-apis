from eth_account import Account


class Signer:
    def __init__(self, private_key: str, chain_id: int):
        if private_key is None:
            msg = "private_key must not be None"
            raise ValueError(msg)
        if chain_id is None:
            msg = "chain_id must not be None"
            raise ValueError(msg)

        self.private_key = private_key
        self.account = Account.from_key(private_key)  # type: ignore[misc]
        self.chain_id = chain_id

    def address(self):
        return self.account.address

    def get_chain_id(self):
        return self.chain_id

    def sign(self, message_hash):
        """Signs a message hash."""
        return Account.unsafe_sign_hash(message_hash, self.private_key).signature.hex()  # type: ignore[misc]
