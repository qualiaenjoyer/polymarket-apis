from typing import cast

from ens.ens import HexStr
from eth_utils.crypto import keccak
from poly_eip712_structs import EIP712Struct, make_domain
from py_order_utils.utils import prepend_zx

from ..signing.model import ClobAuth
from ..signing.signer import Signer

CLOB_DOMAIN_NAME = "ClobAuthDomain"
CLOB_VERSION = "1"
MSG_TO_SIGN = "This message attests that I control the given wallet"


def get_clob_auth_domain(chain_id: int) -> EIP712Struct:
    return make_domain(name=CLOB_DOMAIN_NAME, version=CLOB_VERSION, chainId=chain_id)


def sign_clob_auth_message(signer: Signer, timestamp: int, nonce: int) -> HexStr:
    clob_auth_msg = ClobAuth(
        address=signer.address(),
        timestamp=str(timestamp),
        nonce=nonce,
        message=MSG_TO_SIGN,
    )
    chain_id = signer.get_chain_id()
    auth_struct_hash = cast(  # pyrefly: ignore[redundant-cast]
        "HexStr",
        prepend_zx(
            keccak(clob_auth_msg.signable_bytes(get_clob_auth_domain(chain_id))).hex(),
        ),
    )
    return cast(  # pyrefly: ignore[redundant-cast]
        "HexStr", prepend_zx(signer.sign(auth_struct_hash))
    )
