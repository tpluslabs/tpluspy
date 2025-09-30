from eth_utils import keccak, to_checksum_address


def public_key_to_address(public_key: str | bytes) -> str:
    if isinstance(public_key, bytes):
        public_key = public_key.hex()

    if len(public_key) == 66:
        # Strip off prefix.
        public_key = public_key[2:]

    hashed = keccak(hexstr=public_key)

    # The last 20 bytes are used in the address type.
    address = hashed[-20:]

    return to_checksum_address(address.hex())
