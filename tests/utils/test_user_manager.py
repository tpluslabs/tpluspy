from unittest.mock import patch

import pytest

import tplus.utils.user.manager as manager_mod
from tplus.utils.user.manager import PUBKEY_SUFFIX, UserManager


@pytest.fixture
def manager(tmp_path):
    mgr = UserManager()
    mgr._data_folder = tmp_path
    return mgr


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

    def test_load_does_not_prompt_for_pubkey_access(self, manager, private_key_hex, password):
        manager.add("alice", private_key_hex, password=password)

        prompts: list[str] = []

        def fake_getpass(prompt=""):
            prompts.append(prompt)
            return password

        with patch.object(manager_mod, "getpass", fake_getpass):
            user = manager.load("alice")
            _ = user.public_key
            _ = user.public_key_vec

        assert prompts == []

    def test_load_prompts_only_when_signing(
        self, manager, private_key_hex, expected_sig_hex, password
    ):
        manager.add("alice", private_key_hex, password=password)

        prompts: list[str] = []

        def fake_getpass(prompt=""):
            prompts.append(prompt)
            return password

        with patch.object(manager_mod, "getpass", fake_getpass):
            user = manager.load("alice")
            sig = user.sign("testmessage")

        assert sig.hex() == expected_sig_hex
        assert len(prompts) == 1

    def test_legacy_keyfile_migrates_to_sidecar(
        self, manager, tmp_path, private_key_hex, public_key_hex, password
    ):
        manager.add("alice", private_key_hex, password=password)
        sidecar = tmp_path / f"alice{PUBKEY_SUFFIX}"
        sidecar.unlink()

        prompts: list[str] = []

        def fake_getpass(prompt=""):
            prompts.append(prompt)
            return password

        with patch.object(manager_mod, "getpass", fake_getpass):
            user = manager.load("alice")

        assert user.public_key == public_key_hex
        assert sidecar.is_file()
        assert sidecar.read_text().strip() == public_key_hex
        assert len(prompts) == 1
