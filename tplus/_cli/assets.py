import asyncio
import importlib.util
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
    chain_address_record,
    echo_with_pager,
    ignore_ssl_option,
    no_pager_option,
    output_format_option,
    registry_address_option,
    render,
)

if TYPE_CHECKING:
    from eth_pydantic_types.address import AddressType

    from tplus.evm.contracts import Registry
    from tplus.evm.managers.registry import RegistryOwner


_EVM_AVAILABLE = importlib.util.find_spec("ape") is not None


@click.group()
def assets():
    """Work with assets."""


def _coerce_index(key):
    try:
        return int(key)
    except (TypeError, ValueError):
        return key


def _list_via_oms(cli_ctx: CLIContext, include_risk: bool, output_format: str, no_pager: bool):
    from tplus.model.chain_address import ChainAddress

    client = cli_ctx.orderbook_client(anonymous=True)
    result = asyncio.run(client.assets.get_asset_config())
    risk = asyncio.run(client.assets.get_risk_parameters()) if include_risk else {}
    records = []
    for k, v in result.items():
        rec: dict = {"index": _coerce_index(k)}
        if isinstance(v, dict) and len(v) == 1:
            chain_addr_str, fields = next(iter(v.items()))
            rec.update(chain_address_record(ChainAddress.from_str(chain_addr_str)))
            if isinstance(fields, dict):
                rec["max_deposits"] = fields.get("max_deposits")
                rec["max_1hr_deposits"] = fields.get("max_1hr_deposits")
        else:
            rec["asset"] = v
        if include_risk:
            rec["risk_parameters"] = risk.get(k) or risk.get(str(k))
        records.append(rec)
    records.sort(key=lambda r: r["index"] if isinstance(r["index"], int) else 0)
    render(records, output_format, no_pager=no_pager)


@assets.command("update-ce")
@clearing_url_option()
@ignore_ssl_option()
@pass_cli_context
def _update_ce(cli_ctx: CLIContext):
    """Re-ingest assets from the registry."""
    client = cli_ctx.clearing_engine_client(anonymous=True)
    asyncio.run(client.assets.update())
    click.echo("CE asset update requested.")


@assets.command("get-registry-address")
@output_format_option()
@clearing_url_option()
@ignore_ssl_option()
@pass_cli_context
def _get_registry_address(cli_ctx: CLIContext, output_format: str):
    """Show CE's Registry address."""
    client = cli_ctx.clearing_engine_client(anonymous=True)
    chain_addr = asyncio.run(client.assets.get_registry_address())
    if output_format == "raw":
        click.echo(f"{chain_addr}")
        return

    render([chain_address_record(chain_addr)], output_format)


if _EVM_AVAILABLE:
    from ape.cli import ConnectedProviderCommand, account_option

    from tplus.cli_tools import tplus_network_option

    @assets.command("list")
    @click.option(
        "--oms",
        "use_oms",
        is_flag=True,
        help="Query OMS instead of the Registry contract.",
    )
    @click.option(
        "--include-risk-params",
        "include_risk",
        is_flag=True,
        help="Include risk parameters for each asset.",
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
        include_risk: bool,
        output_format: str,
        no_pager: bool,
        registry_address: str | None,
        provider,
    ):
        """List registered assets."""
        if use_oms:
            _list_via_oms(cli_ctx, include_risk, output_format, no_pager)
            return

        from tplus.evm.contracts import Registry

        with provider.connection():
            registry = Registry.at(registry_address) if registry_address else Registry()
            if not registry.is_deployed:
                render([], output_format, no_pager=no_pager)
                return

            asset_records = registry.get_asset_records()
            risks = registry.get_risk_parameters() if include_risk else []

            if output_format == "raw":
                echo_with_pager([str(r["chain_address"]) for r in asset_records], no_pager=no_pager)
                return

            records = []
            for idx, asset in enumerate(asset_records):
                rec = {
                    "index": idx,
                    **chain_address_record(asset["chain_address"]),
                    "max_deposits": asset["max_deposits"],
                    "max_1hr_deposits": asset["max_1hr_deposits"],
                }
                if include_risk and idx < len(risks):
                    rec["risk_parameters"] = risks[idx].model_dump()
                records.append(rec)
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

    @assets.command("set-risk-manager", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @registry_address_option()
    @tplus_account_option()
    @account_option()
    @click.argument("multisig")
    @pass_cli_context
    def _set_risk_manager(
        cli_ctx: CLIContext, account, multisig: str, registry_address: str | None
    ):
        """Set the Registry's risk manager multisig to MULTISIG."""
        owner = _build_owner(cli_ctx, account, registry_address=registry_address)
        receipt = owner.set_risk_manager_multisig(multisig)
        click.echo(f"tx: {receipt.txn_hash}")

    @assets.command("deploy-registry", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @account_option()
    @click.option(
        "--risk-param-delay",
        "risk_param_delay",
        type=int,
        default=0,
        show_default=True,
        help="Risk-param delay in seconds.",
    )
    @click.option(
        "--skip-if-deployed",
        is_flag=True,
        help="Reuse the CE-registered deployment on this chain if live.",
    )
    def _deploy_registry(account, risk_param_delay: int, skip_if_deployed: bool):
        """Deploy a new Registry."""
        from tplus.evm.contracts import Registry

        if skip_if_deployed and (adopted := Registry()._adopt_ce_deployment()):
            click.echo(f"reused: {adopted.address}")
            return

        instance = Registry.deploy(account, risk_param_delay, sender=account)
        click.echo(f"deployed: {instance.address}")

    @assets.command("set", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @registry_address_option()
    @tplus_account_option()
    @account_option()
    @click.argument("index", type=int)
    @click.argument("asset_address")
    @click.option("--chain-id", "chain_id", type=int, required=True)
    @click.option("--max-deposit", "max_deposit", type=int, required=True)
    @click.option("--max-1hr", "max_1hr_deposits", type=int, required=True)
    @click.option("--min-weight", "min_weight", type=int, required=True)
    @click.option("--no-wait", is_flag=True, help="Don't wait for CE ingestion.")
    @pass_cli_context
    def _set(
        cli_ctx: CLIContext,
        account,
        index: int,
        asset_address: str,
        chain_id: int,
        max_deposit: int,
        max_1hr_deposits: int,
        min_weight: int,
        no_wait: bool,
        registry_address: str | None,
    ):
        """Register asset INDEX at ASSET_ADDRESS."""
        from tplus.model.types import ChainID

        owner = _build_owner(cli_ctx, account, registry_address=registry_address)
        asyncio.run(
            owner.set_asset(
                index=index,
                asset_address=cast("AddressType", asset_address),
                chain_id=ChainID.evm(chain_id),
                max_deposit=max_deposit,
                max_1hr_deposits=max_1hr_deposits,
                min_weight=min_weight,
                wait=not no_wait,
            )
        )
        click.echo(f"Asset {index} registered.")

else:

    @assets.command("list")
    @click.option(
        "--include-risk-params",
        "include_risk",
        is_flag=True,
        help="Include risk parameters for each asset.",
    )
    @output_format_option()
    @no_pager_option()
    @orderbook_url_option()
    @ignore_ssl_option()
    @tplus_account_option()
    @pass_cli_context
    def _list(
        cli_ctx: CLIContext,
        include_risk: bool,
        output_format: str,
        no_pager: bool,
    ):
        """List registered assets.

        Queried from OMS. Reading directly from the Registry contract requires
        the ``[evm]`` extras: ``pip install 'tpluspy[evm]'``.
        """
        _list_via_oms(cli_ctx, include_risk, output_format, no_pager)
