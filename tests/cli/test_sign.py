from tplus._cli import cli

from .conftest import PRIVATE_KEY_HEX


def test_sign(runner, user_dir, signed_message, expected_sig_hex):
    runner.invoke(cli, ["accounts", "add", "eve", "--private-key", PRIVATE_KEY_HEX])
    result = runner.invoke(cli, ["sign", "--tplus-account", "eve", "-m", signed_message])
    assert result.exit_code == 0, result.output
    assert expected_sig_hex in result.output
