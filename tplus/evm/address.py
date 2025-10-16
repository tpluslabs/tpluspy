from typing import TYPE_CHECKING

from eth_keys.datatypes import PublicKey
from eth_utils import keccak, to_checksum_address

if TYPE_CHECKING:
    from ape.types.address import AddressType


def public_key_to_address(public_key: str | bytes) -> "AddressType":
    """
    Convert a secp256k1 public key (compressed or uncompressed) into an Ethereum address.

    Args:
        public_key (str | bytes): The public key in one of the following forms:
            - Hex string (with or without '0x' prefix).
            - Raw bytes.

            Supports:
              - Uncompressed (128 hex chars = 64 bytes, x||y).
              - Compressed   (66 hex chars = 33 bytes, starts with 0x02 or 0x03).

    Returns:
        str: The Ethereum checksum address (EIP-55 format).

    Raises:
        ValueError: If the input is not a valid compressed or uncompressed public key.
    """
    key_bytes = public_key if isinstance(public_key, bytes) else bytes.fromhex(public_key)
    length = len(key_bytes)

    if length == 33:
        # Old CE used to return it this way (the demo one).
        return compressed_public_key_to_address(key_bytes)

    elif length == 64:
        # This is how the CE from main returns it.
        return uncompressed_public_key_to_address(key_bytes)

    raise ValueError(f"Invalid public key '{length}'")


def uncompressed_public_key_to_address(uncompressed_public_key: bytes) -> "AddressType":
    """
    Convert an uncompressed secp256k1 public key to an Ethereum address.

    Args:
        uncompressed_public_key (str): 64-byte hex string representing (x||y).

    Returns:
        str: The Ethereum checksum address.
    """
    # Ethereum address = last 20 bytes of keccak256(pubkey)
    hashed = keccak(uncompressed_public_key)
    return to_checksum_address(hashed[-20:].hex())


def compressed_public_key_to_address(compressed_public_key: bytes) -> "AddressType":
    """
    Convert a compressed secp256k1 public key to an Ethereum address.

    Args:
        compressed_public_key (str): 33-byte compressed public key hex string
            (prefix 0x02 or 0x03 + 32-byte x-coordinate).

    Returns:
        str: The Ethereum checksum address.
    """
    pubkey = PublicKey.from_compressed_bytes(compressed_public_key)
    return pubkey.to_checksum_address()
