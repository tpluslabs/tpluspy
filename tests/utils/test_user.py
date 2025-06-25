from tplus.utils.user import User


class TestUser:
    def test_user_pubkey_size(self):
        expected = 32

        user = User()
        pubkey = user.public_key
        actual = len(bytes.fromhex(pubkey))

        assert actual == expected
