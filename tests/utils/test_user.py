import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # type: ignore
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # type: ignore

from tplus.utils.user import LocalUser, User


class TestUser:
    def test_user_pubkey_size(self):
        expected = 32

        user = User()
        pubkey = user.public_key
        actual = len(bytes.fromhex(pubkey))

        assert actual == expected

    def test_init_with_signing_key(self):
        signing_key = Ed25519PrivateKey.generate()
        user = User(private_key=signing_key)
        assert (
            user.public_key
            == signing_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        )

    def test_hardcoded_key_signature(self, private_key_hex, public_key_hex, expected_sig_hex):
        user = User(private_key=private_key_hex)
        assert user.public_key == public_key_hex
        assert user.sign("testmessage").hex() == expected_sig_hex

    def test_local_user_pubkey_does_not_invoke_unlock(self, private_key_hex, public_key_hex):
        unlocked = []

        def unlock():
            unlocked.append(True)
            return private_key_hex

        user = LocalUser(public_key=public_key_hex, unlock=unlock)

        assert user.public_key == public_key_hex
        assert unlocked == []

    def test_local_user_sign_invokes_unlock_once(
        self, private_key_hex, public_key_hex, expected_sig_hex
    ):
        calls = []

        def unlock():
            calls.append(True)
            return private_key_hex

        user = LocalUser(public_key=public_key_hex, unlock=unlock)

        assert user.sign("testmessage").hex() == expected_sig_hex
        assert user.sign("testmessage").hex() == expected_sig_hex
        assert len(calls) == 1

    def test_local_user_unlock_pubkey_mismatch_raises(self, private_key_hex):
        wrong_pub = "00" * 32
        user = LocalUser(public_key=wrong_pub, unlock=lambda: private_key_hex)

        with pytest.raises(ValueError, match="does not match stored public key"):
            user.sign("testmessage")
