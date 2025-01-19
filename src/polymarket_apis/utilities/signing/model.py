from poly_eip712_structs import Address, EIP712Struct, String, Uint


class ClobAuth(EIP712Struct):
    address = Address()
    timestamp = String()
    nonce = Uint()
    message = String()
