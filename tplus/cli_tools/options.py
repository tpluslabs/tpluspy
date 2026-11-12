import os
from collections.abc import Callable

import click
from eth_pydantic_types.hex.bytes import HexBytes32

from tplus.utils.universe import DEV_UNIVERSE_ENVIRONMENT, Universe, build_dev_universe_name

TPLUS_DEFAULT_BLOCKCHAIN_NETWORK_ENV_VAR = "TPLUS_DEFAULT_BLOCKCHAIN_NETWORK"
TPLUS_DEFAULT_BLOCKCHAIN_NETWORK = "arbitrum:sepolia:"


def tplus_network_option() -> Callable:
    from ape.cli import network_option

    return network_option(
        default=lambda: os.environ.get(
            TPLUS_DEFAULT_BLOCKCHAIN_NETWORK_ENV_VAR, TPLUS_DEFAULT_BLOCKCHAIN_NETWORK
        ),
    )


OUTPUT_FORMATS = ("table", "json", "raw")


def output_format_option() -> Callable:
    return click.option(
        "--output-format",
        "output_format",
        type=click.Choice(OUTPUT_FORMATS, case_sensitive=False),
        default="table",
        envvar="TPLUS_OUTPUT_FORMAT",
        show_default=True,
        help="Output format.",
    )


def no_pager_option() -> Callable:
    return click.option(
        "--no-pager",
        "no_pager",
        is_flag=True,
        default=False,
        envvar="TPLUS_NO_PAGER",
        help="Disable paging output regardless of length.",
    )


def registry_address_option() -> Callable:
    return click.option(
        "--registry-address",
        "registry_address",
        default=None,
        envvar="TPLUS_REGISTRY_ADDRESS",
        help="Override the Registry contract address (bypass tpluspy auto-resolution).",
    )


def op_id_option(**kwargs) -> Callable:
    kwargs.setdefault("required", True)
    kwargs.setdefault("help", "The operation ID the schedule printed.")
    return click.option("--op-id", "op_id", callback=_parse_op_id, **kwargs)


def _parse_op_id(ctx: click.Context, param: click.Parameter, value: str | None) -> bytes | None:
    return None if value is None else bytes(HexBytes32(value))


def vault_address_option() -> Callable:
    return click.option(
        "--vault-address",
        "vault_address",
        default=None,
        envvar="TPLUS_VAULT_ADDRESS",
        help="Override the DepositVault contract address (bypass tpluspy auto-resolution).",
    )


def credential_manager_address_option() -> Callable:
    return click.option(
        "--credential-manager-address",
        "credential_manager_address",
        default=None,
        envvar="TPLUS_CREDENTIAL_MANAGER_ADDRESS",
        help="Override the CredentialManager contract address (bypass tpluspy auto-resolution).",
    )


def ignore_ssl_option() -> Callable:
    def callback(ctx: click.Context, _param, value):
        from tplus._cli._context import CLIContext

        cli_ctx = ctx.ensure_object(CLIContext)
        cli_ctx.ignore_ssl = bool(value)

    return click.option(
        "--ignore-ssl",
        is_flag=True,
        default=False,
        envvar="TPLUS_IGNORE_SSL",
        help="Skip TLS certificate verification. For local dev with self-signed certs.",
        callback=callback,
        expose_value=False,
    )


class UniverseParamType(click.ParamType):
    """A governance universe given as `mainnet`, `staging` or `dev-<environment>`; yields its name."""

    name = "universe"

    def get_metavar(self, param: click.Parameter, ctx: click.Context | None = None) -> str:
        return "[mainnet|staging|dev-<environment>]"

    def convert(self, value, param, ctx) -> str:
        universes_by_name = {universe.name.lower(): universe for universe in Universe}
        environment = value.removeprefix("dev-")
        if value in universes_by_name:
            return universes_by_name[value].value

        if value.startswith("dev-") and environment:
            return build_dev_universe_name(environment)

        choices = ", ".join([*universes_by_name, "dev-<environment>"])
        self.fail(f"{value!r} is not a universe; use one of {choices}", param, ctx)


def universe_option(help: str = "Governance universe.") -> Callable:
    return click.option("--universe", type=UniverseParamType(), help=help)


def resolve_universe(universe: str | None, is_local: bool) -> str:
    """The given universe name, or the local developer universe on a local network."""
    if universe is not None:
        return universe

    if not is_local:
        raise click.UsageError("--universe is required off the local network.")

    return build_dev_universe_name(DEV_UNIVERSE_ENVIRONMENT)


def withdrawal_delay_options() -> Callable:
    def decorate(command: Callable) -> Callable:
        for option in reversed(
            (
                click.option("--min-delay", "min_delay", type=int, default=0, show_default=True),
                click.option("--max-delay", "max_delay", type=int, default=0, show_default=True),
                click.option(
                    "--clamp",
                    "delay_clamps",
                    type=int,
                    multiple=True,
                    help="Delay clamp boundary (repeatable). Defaults to [0, 1_000_000] if omitted.",
                ),
                click.option(
                    "--value",
                    "delay_values",
                    type=int,
                    multiple=True,
                    help="Delay value at each clamp (repeatable). Defaults to [0, 0] if omitted.",
                ),
                click.option(
                    "--cap-floor", "cap_floor", type=int, default=50_000, show_default=True
                ),
            )
        ):
            command = option(command)

        return command

    return decorate


def asset_data_options() -> Callable:
    def decorate(command: Callable) -> Callable:
        for option in reversed(
            (
                click.argument("index", type=int),
                click.argument("asset_address"),
                click.option("--chain-id", "chain_id", type=int, required=True),
                click.option("--max-deposit", "max_deposit", type=int, required=True),
                click.option("--max-1hr", "max_1hr_deposits", type=int, required=True),
                click.option("--min-weight", "min_weight", type=int, required=True),
            )
        ):
            command = option(command)

        return command

    return decorate
