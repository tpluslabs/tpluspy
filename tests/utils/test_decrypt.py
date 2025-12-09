import hashlib
import json

import pytest
from Crypto.Cipher import AES
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from tplus.utils.user.decrypt import decrypt_settlement_approval, ed25519_to_x25519_private_key


def encrypt_to_ed25519_public_key(
    data: bytes, recipient_ed25519_private: Ed25519PrivateKey
) -> tuple[bytes, Ed25519PrivateKey]:
    """
    Simulates what backend does.
    """
    import os

    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    # Generate ephemeral X25519 key pair
    ephemeral_private = X25519PrivateKey.generate()
    ephemeral_public = ephemeral_private.public_key()

    # Convert recipient's Ed25519 private key to X25519
    recipient_x25519_private = ed25519_to_x25519_private_key(recipient_ed25519_private)
    recipient_x25519_public = recipient_x25519_private.public_key()

    shared_secret = ephemeral_private.exchange(recipient_x25519_public)
    encryption_key = hashlib.sha256(shared_secret).digest()

    nonce = os.urandom(12)
    cipher = AES.new(encryption_key, AES.MODE_GCM, nonce=nonce)
    encrypted_payload = cipher.encrypt(data)

    result = bytearray()
    result.extend(ephemeral_public.public_bytes(Encoding.Raw, PublicFormat.Raw))
    result.extend(nonce)
    result.extend(encrypted_payload)

    return bytes(result), recipient_ed25519_private


class TestDecryptSettlementApproval:
    def test_decrypt_settlement_approval_success(self):
        recipient_private_key = Ed25519PrivateKey.generate()
        approval_data = {
            "inner": {
                "signature": [1] * 64,
                "nonce": 42,
            },
            "expiry": 1000000,
            "chain_id": 42161,
        }
        approval_json = json.dumps(approval_data, separators=(",", ":")).encode("utf-8")
        encrypted_data, recipient_key = encrypt_to_ed25519_public_key(
            approval_json, recipient_private_key
        )
        decrypted_data = decrypt_settlement_approval(encrypted_data, recipient_key)

        assert decrypted_data == approval_json
        decrypted_dict = json.loads(decrypted_data)
        assert decrypted_dict == approval_data

    def test_decrypt_settlement_approval_too_short(self):
        recipient_private_key = Ed25519PrivateKey.generate()
        short_data = b"short"
        with pytest.raises(ValueError, match="Encrypted data too short"):
            decrypt_settlement_approval(short_data, recipient_private_key)

    def test_decrypt_settlement_approval_wrong_key(self):
        correct_key = Ed25519PrivateKey.generate()
        wrong_key = Ed25519PrivateKey.generate()

        # Create and encrypt approval data with correct key
        approval_data = {"inner": {"signature": [1] * 64, "nonce": 42}, "expiry": 1000000}
        approval_json = json.dumps(approval_data, separators=(",", ":")).encode("utf-8")

        encrypted_data, _ = encrypt_to_ed25519_public_key(approval_json, correct_key)
        decrypted_data = decrypt_settlement_approval(encrypted_data, wrong_key)
        assert decrypted_data != approval_json

    def test_ed25519_to_x25519_private_key_conversion(self):
        ed25519_key = Ed25519PrivateKey.generate()
        x25519_key = ed25519_to_x25519_private_key(ed25519_key)
        assert isinstance(x25519_key, X25519PrivateKey)
        x25519_public = x25519_key.public_key()
        assert isinstance(x25519_public, X25519PublicKey)

    def test_ed25519_to_x25519_private_key_deterministic(self):
        ed25519_key = Ed25519PrivateKey.generate()
        x25519_key1 = ed25519_to_x25519_private_key(ed25519_key)
        x25519_key2 = ed25519_to_x25519_private_key(ed25519_key)
        x25519_key3 = ed25519_to_x25519_private_key(ed25519_key)
        key1_bytes = x25519_key1.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        key2_bytes = x25519_key2.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        key3_bytes = x25519_key3.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())

        assert key1_bytes == key2_bytes == key3_bytes, "Conversion should be deterministic"
