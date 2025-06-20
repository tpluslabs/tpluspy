from ape.types import AddressType


def to_bytes32(address: str | AddressType) -> bytes:
    """
    In t+, address keys are typically bytes32 to be consistent across chain.
    Use this utility to convert EVM address types to bytes32 by right
    padding with zeroes. We use right-pad because that is how bytes32 values
    are typically stored on chain, as they are not actually scalar types.

    Args:
        address (str | AddressType): The typical size-20 EVM address.

    Returns:
        bytes: Size 32.
    """
    addr_bytes = bytes.fromhex(address[2:])
    return addr_bytes.ljust(32, b"\x00")
