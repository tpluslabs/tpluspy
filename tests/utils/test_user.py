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

    def test_hardcoded_key_signature(self):
        private_key_hex = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
        expected_public_hex = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
        test_message = "testmessage"
        expected_signature_hex = (
            "8ac3a00dd2fd15fc8d15da0c9d6be551402a252e3bf3e7cb96898a33a431cca"
            "26028f5fc0593d9d36909fce914bacb9c0d845146274f74a99f558cac5a4ffc02"
        )

        user = User(private_key=private_key_hex)
        assert user.public_key == expected_public_hex

        signature = user.sign(test_message)
        assert signature.hex() == expected_signature_hex
