import asyncio
import importlib.util
import json
from typing import TYPE_CHECKING, cast

import click

from tplus._cli._context import (
    CLIContext,
    clearing_url_option,
    orderbook_url_option,
    pass_cli_context,
    tplus_account_option,
)
from tplus.cli_tools import (
    ignore_ssl_option,
    no_pager_option,
    output_format_option,
    registry_address_option,
    render,
)

if TYPE_CHECKING:
    from tplus.evm.managers.registry import RegistryOwner


_EVM_AVAILABLE = importlib.util.find_spec("ape") is not None


@click.group()
def params():
    """Manage T+ risk parameters."""


def _coerce_index(key):
    try:
        return int(key)
    except (TypeError, ValueError):
        return key


def _list_via_oms(cli_ctx: CLIContext, output_format: str, no_pager: bool):
    client = cli_ctx.orderbook_client(anonymous=True)
    result = asyncio.run(client.assets.get_risk_parameters())
    records = [{"index": _coerce_index(k), **v} for k, v in result.items()]
    records.sort(key=lambda r: r["index"] if isinstance(r["index"], int) else 0)
    render(records, output_format, no_pager=no_pager)


@params.command("update-ce")
@clearing_url_option()
@ignore_ssl_option()
@pass_cli_context
def _update_ce(cli_ctx: CLIContext):
    """Re-ingest risk params from the registry."""
    client = cli_ctx.clearing_engine_client(anonymous=True)
    asyncio.run(client.assets.update_risk_parameters())
    click.echo("CE risk parameter update requested.")


if _EVM_AVAILABLE:
    from ape.cli import ConnectedProviderCommand, account_option

    from tplus.cli_tools import tplus_network_option

    @params.command("list")
    @click.option(
        "--oms",
        "use_oms",
        is_flag=True,
        help="Query OMS instead of the Registry contract.",
    )
    @output_format_option()
    @no_pager_option()
    @tplus_network_option()
    @orderbook_url_option()
    @ignore_ssl_option()
    @registry_address_option()
    @tplus_account_option()
    @pass_cli_context
    def _list(
        cli_ctx: CLIContext,
        use_oms: bool,
        output_format: str,
        no_pager: bool,
        registry_address: str | None,
        provider,
    ):
        """List risk parameters."""
        if use_oms:
            _list_via_oms(cli_ctx, output_format, no_pager)
            return

        from tplus.evm.contracts import Registry

        with provider.connection():
            registry = Registry.at(registry_address) if registry_address else Registry()
            if not registry.is_deployed:
                render([], output_format, no_pager=no_pager)
                return

            records = [
                {"index": idx, **rp.model_dump()}
                for idx, rp in enumerate(registry.get_risk_parameters())
            ]
            render(records, output_format, no_pager=no_pager)

    def _build_owner(
        cli_ctx: CLIContext, signer, registry_address: str | None = None
    ) -> "RegistryOwner":
        from tplus.evm.contracts import Registry
        from tplus.evm.managers.registry import RegistryOwner

        try:
            ce = cli_ctx.clearing_engine_client(anonymous=True)
        except click.UsageError:
            ce = None
        registry = cast("Registry", Registry.at(registry_address)) if registry_address else None
        return RegistryOwner(owner=signer, registry=registry, clearing_engine=ce)

    @params.command("set", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @registry_address_option()
    @tplus_account_option()
    @account_option()
    @click.argument("index", type=int)
    @click.option("--params", "params_json", required=True, help="Risk parameters as JSON.")
    @pass_cli_context
    def _set(
        cli_ctx: CLIContext,
        account,
        index: int,
        params_json: str,
        registry_address: str | None,
    ):
        """Set pending risk parameters for asset INDEX."""
        owner = _build_owner(cli_ctx, account, registry_address=registry_address)
        receipt = owner.set_pending_risk_parameters(index, json.loads(params_json))
        click.echo(f"tx: {receipt.txn_hash}")

    @params.command("apply", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @registry_address_option()
    @tplus_account_option()
    @account_option()
    @click.argument("index", type=int)
    @pass_cli_context
    def _apply(cli_ctx: CLIContext, account, index: int, registry_address: str | None):
        """Apply pending risk parameters for asset INDEX."""
        owner = _build_owner(cli_ctx, account, registry_address=registry_address)
        receipt = owner.apply_pending_risk_parameters(index)
        click.echo(f"tx: {receipt.txn_hash}")

else:

    @params.command("list")
    @output_format_option()
    @no_pager_option()
    @orderbook_url_option()
    @ignore_ssl_option()
    @tplus_account_option()
    @pass_cli_context
    def _list(
        cli_ctx: CLIContext,
        output_format: str,
        no_pager: bool,
    ):
        """List risk parameters.

        Queried from OMS. Reading directly from the Registry contract requires
        the ``[evm]`` extras: ``pip install 'tpluspy[evm]'``.
        """
        _list_via_oms(cli_ctx, output_format, no_pager)
