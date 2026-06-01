"""
Decrypt data that was sealed to an Ed25519 public key.

This is the inverse of the t+ "encrypt-to-ed25519" scheme: the sender generates
an ephemeral X25519 keypair, performs ECDH against the recipient's (converted)
X25519 key, and encrypts with AES-256-GCM. The sealed blob is laid out as::

    [ephemeral X25519 public key (32 bytes)][nonce (12 bytes)][ciphertext || GCM tag]

These helpers are intentionally generic — they are not tied to any particular
payload type (settlement approvals previously used this, but the helpers are
useful for any data sealed to a user's Ed25519 key).
"""

import hashlib

from Crypto.Cipher import AES
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat


def ed25519_to_x25519_private_key(ed25519_key: Ed25519PrivateKey) -> X25519PrivateKey:
    """Derive the X25519 private key for an Ed25519 private key (SHA-512 of the seed, clamped)."""
    private_bytes = ed25519_key.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )
    seed = private_bytes[:32]

    x25519_secret_bytes = bytearray(hashlib.sha512(seed).digest()[:32])
    x25519_secret_bytes[0] &= 0b11111000
    x25519_secret_bytes[31] &= 0b01111111
    x25519_secret_bytes[31] |= 0b01000000

    return X25519PrivateKey.from_private_bytes(bytes(x25519_secret_bytes))


def decrypt_ed25519_sealed(encrypted_data: bytes, ed25519_private_key: Ed25519PrivateKey) -> bytes:
    """
    Decrypt a blob sealed to an Ed25519 public key, returning the plaintext bytes.

    The sealed format is::

        [ephemeral X25519 public key (32 bytes)][nonce (12 bytes)][ciphertext || GCM tag]

    Args:
        encrypted_data: The sealed blob.
        ed25519_private_key: The recipient's Ed25519 private key.

    Raises:
        ValueError: If ``encrypted_data`` is too short or the GCM tag fails to verify.
    """
    if len(encrypted_data) < 44:
        raise ValueError(
            f"Encrypted data too short: {len(encrypted_data)} bytes (expected at least 44)"
        )

    ephemeral_public_key_bytes = encrypted_data[0:32]
    nonce_bytes = encrypted_data[32:44]
    encrypted_payload = encrypted_data[44:]

    if len(encrypted_payload) < 16:
        raise ValueError("Encrypted payload too short to contain GCM tag")

    ciphertext = encrypted_payload[:-16]
    tag = encrypted_payload[-16:]

    x25519_private_key = ed25519_to_x25519_private_key(ed25519_private_key)
    ephemeral_public_key = X25519PublicKey.from_public_bytes(ephemeral_public_key_bytes)
    shared_secret = x25519_private_key.exchange(ephemeral_public_key)

    encryption_key = hashlib.sha256(shared_secret).digest()

    cipher = AES.new(encryption_key, AES.MODE_GCM, nonce=nonce_bytes)
    plaintext = cipher.decrypt(ciphertext)
    cipher.verify(tag)

    return plaintext
