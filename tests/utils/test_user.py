from ecdsa import SigningKey  # type: ignore

from tplus.utils.user import User


class TestUser:
    def test_user_pubkey_size(self):
        expected = 32

        user = User()
        pubkey = user.public_key
        actual = len(bytes.fromhex(pubkey))

        assert actual == expected

    def test_init_with_signing_key(self):
        signing_key = SigningKey.generate()
        user = User(private_key=signing_key)
        assert user.public_key == signing_key.verifying_key.to_string().hex()
