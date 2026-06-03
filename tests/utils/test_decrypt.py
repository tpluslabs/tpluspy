import hashlib
import json
import os

import pytest
from Crypto.Cipher import AES
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from tplus.utils.user.decrypt import decrypt_ed25519_sealed, ed25519_to_x25519_private_key


def seal_to_ed25519_public_key(data: bytes, recipient_ed25519_private: Ed25519PrivateKey) -> bytes:
    """Simulate what the backend does when sealing data to an Ed25519 key."""
    ephemeral_private = X25519PrivateKey.generate()
    ephemeral_public = ephemeral_private.public_key()

    recipient_x25519_public = ed25519_to_x25519_private_key(recipient_ed25519_private).public_key()

    shared_secret = ephemeral_private.exchange(recipient_x25519_public)
    encryption_key = hashlib.sha256(shared_secret).digest()

    nonce = os.urandom(12)
    cipher = AES.new(encryption_key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(data)

    result = bytearray()
    result.extend(ephemeral_public.public_bytes(Encoding.Raw, PublicFormat.Raw))
    result.extend(nonce)
    result.extend(ciphertext)
    result.extend(tag)
    return bytes(result)


class TestDecryptEd25519Sealed:
    def test_decrypt_success(self):
        recipient_private_key = Ed25519PrivateKey.generate()
        payload = {"inner": {"signature": [1] * 64, "nonce": 42}, "expiry": 1000000}
        payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        encrypted_data = seal_to_ed25519_public_key(payload_json, recipient_private_key)
        decrypted = decrypt_ed25519_sealed(encrypted_data, recipient_private_key)

        assert json.loads(decrypted) == payload

    def test_decrypt_too_short(self):
        recipient_private_key = Ed25519PrivateKey.generate()
        with pytest.raises(ValueError, match="Encrypted data too short"):
            decrypt_ed25519_sealed(b"short", recipient_private_key)

    def test_decrypt_wrong_key(self):
        correct_key = Ed25519PrivateKey.generate()
        wrong_key = Ed25519PrivateKey.generate()
        payload_json = json.dumps({"nonce": 42}, separators=(",", ":")).encode("utf-8")

        encrypted_data = seal_to_ed25519_public_key(payload_json, correct_key)
        with pytest.raises(ValueError):
            decrypt_ed25519_sealed(encrypted_data, wrong_key)

    def test_ed25519_to_x25519_private_key_conversion(self):
        x25519_key = ed25519_to_x25519_private_key(Ed25519PrivateKey.generate())
        assert isinstance(x25519_key, X25519PrivateKey)
        assert isinstance(x25519_key.public_key(), X25519PublicKey)

    def test_ed25519_to_x25519_private_key_deterministic(self):
        ed25519_key = Ed25519PrivateKey.generate()
        keys = [ed25519_to_x25519_private_key(ed25519_key) for _ in range(3)]
        raw = [k.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()) for k in keys]
        assert raw[0] == raw[1] == raw[2], "Conversion should be deterministic"
