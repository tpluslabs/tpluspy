import pytest
from click.testing import CliRunner

from tplus._cli import cli
from tplus.utils.user.manager import UserManager

PRIVATE_KEY_HEX = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
PUBLIC_KEY_HEX = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
PASSWORD = "hunter2"


@pytest.fixture
def user_dir(tmp_path, monkeypatch):
    data = tmp_path / "users"

    def _init(self):
        self._data_folder = data
        self._default_user = None

    monkeypatch.setattr(UserManager, "__init__", _init)
    return data


@pytest.fixture
def runner():
    return CliRunner()


def test_accounts_list_empty(runner, user_dir):
    result = runner.invoke(cli, ["accounts", "list"])
    assert result.exit_code == 0
    assert "No accounts found." in result.output


def test_accounts_add_and_list(runner, user_dir):
    result = runner.invoke(
        cli,
        ["accounts", "add", "alice", "--private-key", PRIVATE_KEY_HEX],
        input=f"{PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    assert PUBLIC_KEY_HEX in result.output

    result = runner.invoke(cli, ["accounts", "list"])
    assert result.exit_code == 0
    assert "alice" in result.output


def test_accounts_add_generate(runner, user_dir):
    result = runner.invoke(
        cli,
        ["accounts", "add", "bob", "--generate"],
        input=f"{PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    assert "bob" in result.output


def test_accounts_add_prompts_for_private_key(runner, user_dir):
    result = runner.invoke(
        cli,
        ["accounts", "add", "carol"],
        input=f"{PRIVATE_KEY_HEX}\n{PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    assert PUBLIC_KEY_HEX in result.output


def test_accounts_show(runner, user_dir):
    runner.invoke(
        cli,
        ["accounts", "add", "dave", "--private-key", PRIVATE_KEY_HEX],
        input=f"{PASSWORD}\n",
    )
    result = runner.invoke(
        cli,
        ["accounts", "show", "dave"],
        input=f"{PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    assert PUBLIC_KEY_HEX in result.output


def test_sign(runner, user_dir):
    runner.invoke(
        cli,
        ["accounts", "add", "eve", "--private-key", PRIVATE_KEY_HEX],
        input=f"{PASSWORD}\n",
    )
    result = runner.invoke(
        cli,
        ["sign", "--account", "eve", "-m", "testmessage"],
        input=f"{PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    expected = (
        "8ac3a00dd2fd15fc8d15da0c9d6be551402a252e3bf3e7cb96898a33a431cca2"
        "6028f5fc0593d9d36909fce914bacb9c0d845146274f74a99f558cac5a4ffc02"
    )
    assert expected in result.output
