import asyncio
from typing import TYPE_CHECKING, cast

import click
from ape.cli import ConnectedProviderCommand, account_option

from tplus._cli._context import (
    CLIContext,
    orderbook_url_option,
    pass_cli_context,
    tplus_account_option,
)
from tplus.cli_tools import ignore_ssl_option, tplus_network_option, vault_address_option

if TYPE_CHECKING:
    from tplus.evm.managers.settle import SettlementManager


@click.group()
def settle():
    """Settle T+ assets on-chain."""


def _settlement_options(f):
    from tplus.model.settlement import SettlementMode

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
        click.option(
            "--settler-executor",
            "settler_executor",
            default=None,
            help=(
                "Address of a contract implementing ``IAtomicSettlementCallback`` to use as "
                "``msg.sender`` for the on-chain ``executeAtomicSettlement``. The vault calls "
                "back into ``msg.sender.onAtomicSettlement``, so an EOA won't work. On local "
                "networks ape impersonates the contract; in prod the deployed contract handles "
                "the callback itself."
            ),
        ),
    ]
    for option in reversed(options):
        f = option(f)
    return f


def _build_manager(
    cli_ctx: CLIContext, signer, vault_address: str | None = None
) -> "SettlementManager":
    from tplus.evm.contracts import DepositVault
    from tplus.evm.managers.settle import SettlementManager

    vault = cast("DepositVault", DepositVault.at(vault_address)) if vault_address else None
    return SettlementManager(
        default_user=cli_ctx.load_user(),
        ape_account=signer,
        oms_client=cli_ctx.orderbook_client(),
        vault=vault,
    )


def _run_init(manager: "SettlementManager", kwargs: dict, *, then_execute: bool):
    from tplus.evm.dev.contracts import SettlerExecutor
    from tplus.model.asset_identifier import Address32
    from tplus.model.settlement import SettlementMode
    from tplus.utils.amount import Amount

    asset_in = Address32(kwargs["asset_in"])
    asset_out = Address32(kwargs["asset_out"])
    amount_in = Amount(amount=kwargs["amount_in"], decimals=kwargs["amount_in_decimals"])
    amount_out = Amount(amount=kwargs["amount_out"], decimals=kwargs["amount_out_decimals"])
    mode = SettlementMode[kwargs["mode"].upper()]

    executor_contract = None
    if executor_address := kwargs.get("settler_executor"):
        executor_contract = SettlerExecutor.at(executor_address)

    info, _approval = asyncio.run(
        manager.init_settlement(
            asset_in=asset_in,
            amount_in=amount_in,
            asset_out=asset_out,
            amount_out=amount_out,
            mode=mode,
            then_execute=then_execute,
            executor_contract=executor_contract,
        )
    )
    return info


@settle.command("init", cls=ConnectedProviderCommand)
@tplus_network_option()
@orderbook_url_option()
@ignore_ssl_option()
@vault_address_option()
@tplus_account_option()
@account_option()
@_settlement_options
@pass_cli_context
def _init(cli_ctx: CLIContext, account, vault_address: str | None, **kwargs):
    """Initialize a settlement on the clearing engine."""
    manager = _build_manager(cli_ctx, account, vault_address=vault_address)
    info = _run_init(manager, kwargs, then_execute=False)
    click.echo(f"Settlement initialized. Nonce: {info.nonce}")


@settle.command("execute", cls=ConnectedProviderCommand)
@tplus_network_option()
@orderbook_url_option()
@ignore_ssl_option()
@vault_address_option()
@tplus_account_option()
@account_option()
@_settlement_options
@pass_cli_context
def _execute(cli_ctx: CLIContext, account, vault_address: str | None, **kwargs):
    """Initialize and execute a settlement on-chain once approved."""
    manager = _build_manager(cli_ctx, account, vault_address=vault_address)
    info = _run_init(manager, kwargs, then_execute=True)
    click.echo(f"Settlement executed. Nonce: {info.nonce}")
