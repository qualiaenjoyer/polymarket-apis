from typing import TYPE_CHECKING, Any

from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_typing import ChecksumAddress, HexStr

if TYPE_CHECKING:
    from eth_account.datastructures import SignedMessage
    from eth_account.signers.local import LocalAccount


class Signer:
    def __init__(self, private_key: str, chain_id: int):
        if private_key is None:
            msg = "private_key must not be None"
            raise ValueError(msg)
        if chain_id is None:
            msg = "chain_id must not be None"
            raise ValueError(msg)

        self.private_key = private_key
        self.account: LocalAccount = Account.from_key(private_key)
        self.chain_id = chain_id

    def address(self) -> ChecksumAddress:
        return self.account.address

    def get_chain_id(self) -> int:
        return self.chain_id

    def sign(self, message_hash: HexStr | bytes | int) -> str:
        """Signs a message hash."""
        signed_hash: SignedMessage = Account.unsafe_sign_hash(
            message_hash, self.private_key
        )
        return signed_hash.signature.hex()

    def sign_typed_data(self, full_message: dict[str, Any]) -> str:
        """Signs EIP-712 typed data."""
        message = encode_typed_data(full_message=full_message)
        signed_message: SignedMessage = Account.sign_message(
            message, self.private_key
        )
        return f"0x{signed_message.signature.hex()}"
