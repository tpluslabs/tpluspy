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
    asset_data_options,
    chain_address_record,
    describe_schedule_event,
    echo_with_pager,
    ignore_ssl_option,
    no_pager_option,
    op_id_option,
    output_format_option,
    registry_address_option,
    render,
    resolve_universe,
    universe_option,
)
from tplus.utils.universe import compute_universe_id

if TYPE_CHECKING:
    from collections.abc import Iterable

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

    @assets.command("init-risk-council", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @registry_address_option()
    @tplus_account_option()
    @account_option()
    @click.argument("credential_manager")
    @universe_option(
        help="Governance universe of CREDENTIAL_MANAGER. Required off the local network."
    )
    @click.option(
        "--member",
        "members",
        multiple=True,
        help="Risk council member address. May be repeated. Defaults to the sender.",
    )
    @click.option("--threshold", type=int, help="Defaults to a strict majority of the members.")
    @pass_cli_context
    def _init_risk_council(
        cli_ctx: CLIContext,
        account,
        credential_manager: str,
        universe: str | None,
        members: "Iterable[str]",
        threshold: int | None,
        registry_address: str | None,
        provider,
    ):
        """Install the Registry's risk council, governed by CREDENTIAL_MANAGER."""
        from tplus.evm.contracts import ZERO_ADDRESS
        from tplus.evm.governance import compute_majority_threshold

        owner = _build_owner(cli_ctx, account, registry_address=registry_address)
        if owner.registry.get_credential_manager() != ZERO_ADDRESS:
            click.echo("risk council already installed")
            return

        universe_id = bytes(
            compute_universe_id(resolve_universe(universe, provider.network.is_local))
        )

        council = list(members) or [account.address]
        receipt = owner.initialize_risk_council(
            credential_manager,
            universe_id,
            council,
            threshold or compute_majority_threshold(len(council)),
        )
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
        "--upgrade-delay",
        "upgrade_delay",
        type=int,
        default=0,
        show_default=True,
        help=(
            "Proxy upgrade delay in seconds. Mainnet needs a non-zero delay unless "
            "--allow-zero-upgrade-delay is passed."
        ),
    )
    @click.option(
        "--allow-zero-upgrade-delay",
        is_flag=True,
        help=(
            "Allow a zero upgrade delay on mainnet for bootstrap; raise it before relying on "
            "the upgrade timelock."
        ),
    )
    @click.option(
        "--skip-if-deployed",
        is_flag=True,
        help="Reuse the CE-registered deployment on this chain if live.",
    )
    def _deploy_registry(
        provider,
        account,
        risk_param_delay: int,
        upgrade_delay: int,
        allow_zero_upgrade_delay: bool,
        skip_if_deployed: bool,
    ):
        """Deploy a new Registry behind an ERC1967 proxy."""
        from tplus.evm.contracts import Registry

        if skip_if_deployed and (adopted := Registry()._adopt_ce_deployment()):
            click.echo(f"reused: {adopted.address}")
            return

        if provider.network.is_mainnet and upgrade_delay == 0:
            if not allow_zero_upgrade_delay:
                raise click.UsageError(
                    "Pass a non-zero --upgrade-delay on mainnet, or --allow-zero-upgrade-delay "
                    "for bootstrap; with a zero delay the admin can upgrade the Registry at once."
                )

            click.echo(
                "The Registry starts with a zero upgrade delay; raise it before relying on the "
                "upgrade timelock."
            )

        instance = Registry.deploy_proxy(
            sender=account, risk_param_delay_secs=risk_param_delay, upgrade_delay_secs=upgrade_delay
        )
        click.echo(f"deployed: {instance.address}")

    @assets.command("set", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @registry_address_option()
    @tplus_account_option()
    @account_option()
    @asset_data_options()
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
        from tplus.evm.governance import is_operation_due
        from tplus.model.types import ChainID

        owner = _build_owner(cli_ctx, account, registry_address=registry_address)
        schedule_event = asyncio.run(
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
        if is_operation_due(schedule_event, owner.registry.backend):
            click.echo(f"Asset {index} registered.")
        else:
            click.echo(f"Asset {index} {describe_schedule_event(schedule_event)}")

    @assets.command("execute", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @registry_address_option()
    @tplus_account_option()
    @account_option()
    @asset_data_options()
    @op_id_option()
    @pass_cli_context
    def _execute(
        cli_ctx: CLIContext,
        account,
        index: int,
        asset_address: str,
        chain_id: int,
        max_deposit: int,
        max_1hr_deposits: int,
        min_weight: int,
        op_id: bytes,
        registry_address: str | None,
    ):
        """Execute the asset entry scheduled for INDEX, then request CE ingestion."""
        from tplus.evm.contracts import Registry
        from tplus.model.types import ChainID

        owner = _build_owner(cli_ctx, account, registry_address=registry_address)
        data = Registry.build_asset_data(
            index,
            cast("AddressType", asset_address),
            ChainID.evm(chain_id),
            max_deposit,
            max_1hr_deposits,
            min_weight,
        )
        receipt = owner.execute_operation("ASSET_DATA", [data], op_id)
        click.echo(f"tx: {receipt.txn_hash}")
        if ce := owner.ce:
            asyncio.run(ce.assets.update())
            click.echo("CE asset update requested.")

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
