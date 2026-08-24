import pytest

import tplus.utils.user.manager as manager_mod
from tplus.utils.user.manager import PUBKEY_SUFFIX, UserManager


@pytest.fixture
def manager(tmp_path):
    mgr = UserManager()
    mgr._data_folder = tmp_path
    return mgr


@pytest.fixture
def getpass(mocker, password):
    """The password prompt, so ``call_count`` is the number of times the user was asked."""
    return mocker.patch.object(manager_mod, "getpass", return_value=password)


class TestUserManager:
    def test_add_writes_pubkey_sidecar(
        self, manager, tmp_path, private_key_hex, public_key_hex, password
    ):
        manager.add("alice", private_key_hex, password=password)

        sidecar = tmp_path / f"alice{PUBKEY_SUFFIX}"
        assert sidecar.is_file()
        assert sidecar.read_text().strip() == public_key_hex

    def test_usernames_excludes_pubkey_files(self, manager, private_key_hex, password):
        manager.add("alice", private_key_hex, password=password)
        assert list(manager.usernames) == ["alice"]

    def test_load_does_not_prompt_for_pubkey_access(
        self, manager, private_key_hex, password, getpass
    ):
        manager.add("alice", private_key_hex, password=password)

        user = manager.load("alice")
        _ = user.public_key
        _ = user.public_key_vec

        assert getpass.call_count == 0

    def test_load_prompts_only_when_signing(
        self, manager, private_key_hex, signed_message, expected_sig_hex, password, getpass
    ):
        manager.add("alice", private_key_hex, password=password)

        user = manager.load("alice")
        sig = user.sign(signed_message)

        assert sig.hex() == expected_sig_hex
        assert getpass.call_count == 1

    def test_legacy_keyfile_migrates_to_sidecar(
        self, manager, tmp_path, private_key_hex, public_key_hex, password, getpass
    ):
        manager.add("alice", private_key_hex, password=password)
        sidecar = tmp_path / f"alice{PUBKEY_SUFFIX}"
        sidecar.unlink()

        user = manager.load("alice")

        assert user.public_key == public_key_hex
        assert sidecar.is_file()
        assert sidecar.read_text().strip() == public_key_hex
        assert getpass.call_count == 1

    def test_load_from_evm_account(self, manager, eth_account, expected_user_id):
        assert manager.load_from_evm_account(eth_account).public_key == expected_user_id

    def test_load_from_evm_account_holds_derivation(self, manager, eth_account):
        # Deriving costs a signature (and may prompt), so the same account resolves once.
        assert manager.load_from_evm_account(eth_account) is manager.load_from_evm_account(
            eth_account
        )

    def test_load_from_evm_account_sub_account(self, manager, eth_account):
        main = manager.load_from_evm_account(eth_account)
        second = manager.load_from_evm_account(eth_account, sub_account=1)

        assert second is not main
        assert second.sub_account == 1
        assert second.public_key == main.public_key
