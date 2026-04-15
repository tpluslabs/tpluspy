import asyncio

import click
from ape.cli import ConnectedProviderCommand, account_option

from tplus._cli._context import CLIContext, pass_cli_context
from tplus.evm.managers.settle import SettlementManager
from tplus.model.asset_identifier import Address32
from tplus.model.settlement import SettlementMode
from tplus.utils.amount import Amount


@click.group()
def settle():
    """Settle T+ assets on-chain."""


def _settlement_options(f):
    options = [
        click.option("--asset-in", "asset_in", required=True, help="32-byte hex asset in."),
        click.option("--amount-in", "amount_in", type=int, required=True, help="Atomic amount in."),
        click.option(
            "--amount-in-decimals",
            "amount_in_decimals",
            type=int,
            required=True,
            help="Decimals for amount in.",
        ),
        click.option("--asset-out", "asset_out", required=True, help="32-byte hex asset out."),
        click.option(
            "--amount-out", "amount_out", type=int, required=True, help="Atomic amount out."
        ),
        click.option(
            "--amount-out-decimals",
            "amount_out_decimals",
            type=int,
            required=True,
            help="Decimals for amount out.",
        ),
        click.option(
            "--mode",
            type=click.Choice([m.name for m in SettlementMode], case_sensitive=False),
            default=SettlementMode.MARGIN.name,
            show_default=True,
        ),
    ]
    for option in reversed(options):
        f = option(f)
    return f


def _build_manager(cli_ctx: CLIContext, signer) -> SettlementManager:
    return SettlementManager(
        default_user=cli_ctx.load_user(),
        ape_account=signer,
        clearing_engine=cli_ctx.clearing_engine_client(),
    )


def _run_init(manager: SettlementManager, kwargs: dict, *, then_execute: bool):
    asset_in = Address32(kwargs["asset_in"])
    asset_out = Address32(kwargs["asset_out"])
    amount_in = Amount(amount=kwargs["amount_in"], decimals=kwargs["amount_in_decimals"])
    amount_out = Amount(amount=kwargs["amount_out"], decimals=kwargs["amount_out_decimals"])
    mode = SettlementMode[kwargs["mode"].upper()]

    return asyncio.run(
        manager.init_settlement(
            asset_in=asset_in,
            amount_in=amount_in,
            asset_out=asset_out,
            amount_out=amount_out,
            mode=mode,
            then_execute=then_execute,
        )
    )


@settle.command("init", cls=ConnectedProviderCommand)
@account_option()
@_settlement_options
@pass_cli_context
def _init(cli_ctx: CLIContext, account, **kwargs):
    """Initialize a settlement on the clearing engine."""
    manager = _build_manager(cli_ctx, account)
    info = _run_init(manager, kwargs, then_execute=False)
    click.echo(f"Settlement initialized. Nonce: {info.nonce}")


@settle.command("execute", cls=ConnectedProviderCommand)
@account_option()
@_settlement_options
@pass_cli_context
def _execute(cli_ctx: CLIContext, account, **kwargs):
    """Initialize and execute a settlement on-chain once approved."""
    manager = _build_manager(cli_ctx, account)
    info = _run_init(manager, kwargs, then_execute=True)
    click.echo(f"Settlement executed. Nonce: {info.nonce}")
