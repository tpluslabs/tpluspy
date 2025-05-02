from ape.types import AddressType


def address_to_bytes32(address: str | AddressType) -> bytes:
    """
    In t+, address keys are typically bytes32 to be consistent across chain.
    Use this utility to convert EVM address types to bytes32 by left
    padding with zeroes.

    Args:
        address (str | AddressType): The typical size-20 EVM address.

    Returns:
        bytes: Size 32.
    """
    addr_bytes = bytes.fromhex(address[2:])
    return addr_bytes.rjust(32, b"\x00")
