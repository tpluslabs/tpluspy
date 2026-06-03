from tplus._cli import cli

from .conftest import PRIVATE_KEY_HEX


def test_sign(runner, user_dir):
    runner.invoke(cli, ["accounts", "add", "eve", "--private-key", PRIVATE_KEY_HEX])
    result = runner.invoke(cli, ["sign", "--tplus-account", "eve", "-m", "testmessage"])
    assert result.exit_code == 0, result.output
    expected = (
        "8ac3a00dd2fd15fc8d15da0c9d6be551402a252e3bf3e7cb96898a33a431cca2"
        "6028f5fc0593d9d36909fce914bacb9c0d845146274f74a99f558cac5a4ffc02"
    )
    assert expected in result.output
