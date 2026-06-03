import os
from collections.abc import Callable

import click

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
