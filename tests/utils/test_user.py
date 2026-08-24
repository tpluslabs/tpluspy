import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # type: ignore
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # type: ignore

from tplus.utils.user import DelegatedUser, LocalUser, User, to_user, to_user_public_key


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

    def test_hardcoded_key_signature(
        self, private_key_hex, public_key_hex, signed_message, expected_sig_hex
    ):
        user = User(private_key=private_key_hex)
        assert user.public_key == public_key_hex
        assert user.sign(signed_message).hex() == expected_sig_hex

    def test_local_user_pubkey_does_not_invoke_unlock(self, private_key_hex, public_key_hex):
        unlocked = []

        def unlock():
            unlocked.append(True)
            return private_key_hex

        user = LocalUser(public_key=public_key_hex, unlock=unlock)

        assert user.public_key == public_key_hex
        assert unlocked == []

    def test_local_user_sign_invokes_unlock_once(
        self, private_key_hex, public_key_hex, signed_message, expected_sig_hex
    ):
        calls = []

        def unlock():
            calls.append(True)
            return private_key_hex

        user = LocalUser(public_key=public_key_hex, unlock=unlock)

        assert user.sign(signed_message).hex() == expected_sig_hex
        assert user.sign(signed_message).hex() == expected_sig_hex
        assert len(calls) == 1

    def test_local_user_unlock_pubkey_mismatch_raises(self, private_key_hex):
        wrong_pub = "00" * 32
        user = LocalUser(public_key=wrong_pub, unlock=lambda: private_key_hex)

        with pytest.raises(ValueError, match="does not match stored public key"):
            user.sign("testmessage")

    def test_delegated_user_targets_account_and_emits_additional_signature(self):
        account = User()
        signer = User()
        user = DelegatedUser(account.public_key, signer, sub_account=2)

        master_signature, additional = user.signing_parts("payload")

        assert user.public_key == account.public_key
        assert user.sub_account == 2
        assert master_signature == []
        assert len(additional) == 1
        assert additional[0].signer.model_dump() == {"Ed25519": signer.public_key_vec}
        signer.vk.verify(bytes(additional[0].signature), b"payload")

    def test_delegated_user_defaults_to_main_sub_account(self):
        user = DelegatedUser(User().public_key, User())

        assert user.sub_account == 0

    @pytest.mark.parametrize("attribute", ["sk", "vk"])
    def test_delegated_user_has_no_account_master_key(self, attribute):
        user = DelegatedUser(User().public_key, User())

        with pytest.raises(AttributeError, match="no account master"):
            getattr(user, attribute)
        assert not hasattr(user, attribute)
        assert getattr(user, attribute, None) is None

    def test_delegated_user_rejects_direct_signing(self):
        user = DelegatedUser(User().public_key, User())

        with pytest.raises(ValueError, match="cannot produce master signatures"):
            user.sign("payload")

    def test_delegated_user_rejects_nested_delegation(self):
        delegated_signer = DelegatedUser(User().public_key, User())

        with pytest.raises(ValueError, match="not another DelegatedUser"):
            DelegatedUser(User().public_key, delegated_signer)

    @pytest.mark.parametrize("account", ["short", "zz" * 32])
    def test_delegated_user_rejects_invalid_account_public_key(self, account):
        with pytest.raises(ValueError, match="account_public_key"):
            DelegatedUser(account, User())

    def test_from_eth_account_matches_browser_vector(self, eth_account, eth_user, expected_user_id):
        assert eth_user.public_key == expected_user_id
        assert eth_user.evm_address == eth_account.address

    def test_from_eth_account_signs_like_native_user(self, eth_user):
        assert eth_user.sign("hello") == User(private_key=eth_user.sk).sign("hello")


def test_to_user_user():
    user = User()

    assert to_user(user) is user


def test_to_user_evm_account(eth_account, expected_user_id):
    assert to_user(eth_account).public_key == expected_user_id


def test_to_user_public_key_raises(expected_user_id):
    with pytest.raises(TypeError, match="Cannot sign with"):
        to_user(expected_user_id)  # type: ignore[arg-type]


def test_to_user_public_key_passes_through_str(expected_user_id):
    assert to_user_public_key(expected_user_id) == expected_user_id


def test_to_user_public_key_evm_account(eth_account, expected_user_id):
    assert to_user_public_key(eth_account) == expected_user_id
