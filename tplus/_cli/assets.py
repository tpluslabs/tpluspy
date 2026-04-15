import asyncio
import json

import click
from ape.cli import ConnectedProviderCommand, account_option, network_option

from tplus._cli._context import CLIContext, pass_cli_context
from tplus.evm.contracts import Registry
from tplus.evm.managers.registry import RegistryOwner
from tplus.model.types import ChainID


@click.group()
def assets():
    """Manage T+ asset registry."""


@assets.command("list")
@click.option(
    "--ce",
    "--clearing-engine",
    "use_ce",
    is_flag=True,
    help="Query the clearing engine instead of the Registry contract.",
)
@network_option()
@pass_cli_context
def _list(cli_ctx: CLIContext, use_ce: bool, network):
    """List registered assets."""
    if use_ce:
        client = cli_ctx.clearing_engine_client()
        result = asyncio.run(client.assets.get())
        click.echo(json.dumps(result, indent=2, default=str))
        return

    from ape import networks

    with networks.parse_network_choice(network):
        for address in Registry().get_asset_addresses():
            click.echo(address)


def _build_owner(cli_ctx: CLIContext, signer) -> RegistryOwner:
    return RegistryOwner(owner=signer, clearing_engine=cli_ctx.clearing_engine_client())


@assets.command("set", cls=ConnectedProviderCommand)
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
):
    """Register asset INDEX at ASSET_ADDRESS."""
    owner = _build_owner(cli_ctx, account)
    asyncio.run(
        owner.set_asset(
            index=index,
            asset_address=asset_address,
            chain_id=ChainID.evm(chain_id),
            max_deposit=max_deposit,
            max_1hr_deposits=max_1hr_deposits,
            min_weight=min_weight,
            wait=not no_wait,
        )
    )
    click.echo(f"Asset {index} registered.")


@assets.command("set-risk", cls=ConnectedProviderCommand)
@account_option()
@click.argument("index", type=int)
@click.option("--params", "params_json", required=True, help="Risk parameters as JSON.")
@pass_cli_context
def _set_risk(cli_ctx: CLIContext, account, index: int, params_json: str):
    """Set pending risk parameters for asset INDEX."""
    owner = _build_owner(cli_ctx, account)
    receipt = owner.set_pending_risk_parameters(index, json.loads(params_json))
    click.echo(f"tx: {receipt.txn_hash}")


@assets.command("apply-risk", cls=ConnectedProviderCommand)
@account_option()
@click.argument("index", type=int)
@pass_cli_context
def _apply_risk(cli_ctx: CLIContext, account, index: int):
    """Apply pending risk parameters for asset INDEX."""
    owner = _build_owner(cli_ctx, account)
    receipt = owner.apply_pending_risk_parameters(index)
    click.echo(f"tx: {receipt.txn_hash}")
