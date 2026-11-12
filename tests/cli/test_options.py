import click
import pytest
from click.testing import CliRunner

from tplus.cli_tools import resolve_universe, universe_option
from tplus.utils.universe import DEV_UNIVERSE_ENVIRONMENT, build_dev_universe_name


@pytest.fixture(scope="session")
def universe_command():
    @click.command()
    @universe_option()
    def echo_universe(universe: str | None):
        click.echo(universe)

    return echo_universe


@pytest.mark.parametrize(
    "value, name",
    [
        pytest.param("mainnet", "tplus-mainnet", id="mainnet"),
        pytest.param("staging", "tplus-staging", id="staging"),
        pytest.param("dev-example", "tplus-dev-example", id="dev-environment"),
    ],
)
def test_universe_option_yields_the_universe_name(universe_command, value, name):
    result = CliRunner().invoke(universe_command, ["--universe", value])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == name


@pytest.mark.parametrize("value", ["tplus-mainnet", "dev-", "testnet"])
def test_universe_option_rejects_unknown_names(universe_command, value):
    result = CliRunner().invoke(universe_command, ["--universe", value])
    assert result.exit_code != 0
    assert "is not a universe" in result.output


def test_universe_option_lists_the_choices_in_help(universe_command):
    result = CliRunner().invoke(universe_command, ["--help"])
    assert "[mainnet|staging|dev-<environment>]" in result.output


@pytest.mark.parametrize(
    "universe, is_local, name",
    [
        pytest.param("tplus-staging", False, "tplus-staging", id="given-off-local"),
        pytest.param("tplus-staging", True, "tplus-staging", id="given-on-local"),
        pytest.param(
            None, True, build_dev_universe_name(DEV_UNIVERSE_ENVIRONMENT), id="local-default"
        ),
    ],
)
def test_resolve_universe_fixes_the_deployed_universe(universe, is_local, name):
    assert resolve_universe(universe, is_local) == name


def test_resolve_universe_requires_a_universe_off_the_local_network():
    with pytest.raises(click.UsageError, match="--universe is required"):
        resolve_universe(None, is_local=False)
