from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # type: ignore
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # type: ignore

from tplus.utils.user import User


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
