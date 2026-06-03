from tplus._cli import cli

from .conftest import PRIVATE_KEY_HEX, PUBLIC_KEY_HEX


def test_accounts_list_empty(runner, user_dir):
    result = runner.invoke(cli, ["accounts", "list"])
    assert result.exit_code == 0
    assert "No accounts found." in result.output


def test_accounts_add_and_list(runner, user_dir):
    result = runner.invoke(cli, ["accounts", "add", "alice", "--private-key", PRIVATE_KEY_HEX])
    assert result.exit_code == 0, result.output
    assert PUBLIC_KEY_HEX in result.output

    result = runner.invoke(cli, ["accounts", "list"])
    assert result.exit_code == 0
    assert "alice" in result.output


def test_accounts_generate(runner, user_dir):
    result = runner.invoke(cli, ["accounts", "generate", "bob"])
    assert result.exit_code == 0, result.output
    assert "bob" in result.output


def test_accounts_add_prompts_for_private_key(runner, user_dir):
    result = runner.invoke(
        cli,
        ["accounts", "add", "carol"],
        input=f"{PRIVATE_KEY_HEX}\n",
    )
    assert result.exit_code == 0, result.output
    assert PUBLIC_KEY_HEX in result.output


def test_accounts_show(runner, user_dir):
    runner.invoke(cli, ["accounts", "add", "dave", "--private-key", PRIVATE_KEY_HEX])
    result = runner.invoke(cli, ["accounts", "show", "dave"])
    assert result.exit_code == 0, result.output
    assert PUBLIC_KEY_HEX in result.output
