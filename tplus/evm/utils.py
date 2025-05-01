from ape.types import AddressType


def address_to_bytes32(address: str | AddressType) -> bytes:
    addr_bytes = bytes.fromhex(address[2:])
    return addr_bytes.rjust(32, b"\x00")
