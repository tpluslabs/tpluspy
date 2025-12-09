"""
Utilities for decrypting settlement approval messages encrypted to Ed25519 public keys.
"""

import hashlib
import json

from Crypto.Cipher import AES
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat


def ed25519_to_x25519_private_key(ed25519_key: Ed25519PrivateKey) -> X25519PrivateKey:
    """
    Convert an Ed25519 private key to an X25519 private key.

    The conversion process:
    1. Get the seed bytes from the Ed25519 private key
    2. Hash the seed through SHA-512
    3. Take the first 32 bytes of the hash
    4. Clamp the bytes for X25519 (clear top bit, set second-to-top, clear bottom 3 bits)
    5. Create an X25519 private key from the clamped bytes

    Args:
        ed25519_key: The Ed25519 private key to convert

    Returns:
        An X25519 private key derived from the Ed25519 key
    """
    # Get the seed bytes (32 bytes) from the Ed25519 private key
    private_bytes = ed25519_key.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )
    # The seed is the first 32 bytes
    seed = private_bytes[:32]

    # Hash the seed through SHA-512 for proper Ed25519 to X25519 conversion
    hash_result = hashlib.sha512(seed).digest()

    # Take the first 32 bytes
    x25519_secret_bytes = bytearray(hash_result[:32])

    # Clamp the bytes for X25519:
    # - Clear the top bit (bit 7 of byte 0)
    x25519_secret_bytes[0] &= 0b11111000  # Clear bottom 3 bits
    # - Set the second-to-top bit (bit 6 of byte 31)
    x25519_secret_bytes[31] &= 0b01111111  # Clear top bit
    x25519_secret_bytes[31] |= 0b01000000  # Set second-to-top bit

    # Create X25519 private key from the clamped bytes
    return X25519PrivateKey.from_private_bytes(bytes(x25519_secret_bytes))


def decrypt_settlement_approval(
    encrypted_data: bytes, ed25519_private_key: Ed25519PrivateKey
) -> dict:
    """
    Decrypt a settlement approval message that was encrypted to an Ed25519 public key.

    The encrypted data format is:
    - First 32 bytes: Ephemeral X25519 public key
    - Next 12 bytes: Nonce for AES-GCM
    - Remaining bytes: Encrypted payload (AES-256-GCM encrypted)

    Decryption process:
    1. Extract ephemeral public key, nonce, and encrypted payload
    2. Convert Ed25519 private key to X25519
    3. Perform X25519 ECDH to derive shared secret
    4. Derive AES-256-GCM encryption key using SHA-256 of shared secret
    5. Decrypt the payload

    Args:
        encrypted_data: The encrypted data as received from the WebSocket
        ed25519_private_key: The Ed25519 private key of the settler

    Returns:
        The decrypted approval JSON dictionary

    Raises:
        ValueError: If encrypted_data is too short or decryption fails
    """
    if len(encrypted_data) < 44:
        raise ValueError(
            f"Encrypted data too short: {len(encrypted_data)} bytes (expected at least 44)"
        )

    # Extract components
    ephemeral_public_key_bytes = encrypted_data[0:32]
    nonce_bytes = encrypted_data[32:44]
    encrypted_payload = encrypted_data[44:]

    # Split ciphertext and tag
    if len(encrypted_payload) < 16:
        raise ValueError("Encrypted payload too short to contain GCM tag")

    ciphertext = encrypted_payload[:-16]
    tag = encrypted_payload[-16:]

    # Convert Ed25519 private key to X25519
    x25519_private_key = ed25519_to_x25519_private_key(ed25519_private_key)

    ephemeral_public_key = X25519PublicKey.from_public_bytes(ephemeral_public_key_bytes)
    shared_secret = x25519_private_key.exchange(ephemeral_public_key)

    # Derive AES key
    encryption_key = hashlib.sha256(shared_secret).digest()

    # AES-GCM decrypt + verify
    cipher = AES.new(encryption_key, AES.MODE_GCM, nonce=nonce_bytes)
    plaintext = cipher.decrypt(ciphertext)

    cipher.verify(tag)

    json_data = plaintext.decode("utf-8")
    return json.loads(json_data)
