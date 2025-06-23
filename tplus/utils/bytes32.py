def to_bytes32(address: str, pad: str = "r") -> bytes:
    """
    In t+, address keys are typically bytes32 to be consistent across chain.
    Use this utility to convert EVM address types to bytes32. For bytes32 storage
    values, such as assets in the registry, use right-padding. Use left padding
    for encoding 20-bytes addresses into EVM word sizes.

    Args:
        address (str | AddressType): The typical size-20 EVM address.
        pad (str): "right" or "r" for pad right; else pads left. Defaults to "right".

    Returns:
        bytes: Size 32.
    """
    address_str = address[2:] if address.startswith("0x") else address
    addr_bytes = bytes.fromhex(address_str)
    if pad in ("right", "r"):
        return addr_bytes.ljust(32, b"\x00")

    elif pad in ("left", "l"):
        return addr_bytes.rjust(32, b"\x00")

    raise ValueError(f"Unknown pad value {pad}")
