import asyncio
import json

import click
from ape.cli import ConnectedProviderCommand, account_option

from tplus._cli._context import CLIContext, pass_cli_context
from tplus.evm.managers.withdraw import WithdrawalManager
from tplus.model.withdrawal import CancelWithdrawalRequest


@click.group()
def withdraw():
    """Withdraw T+ assets."""


def _withdrawal_options(f):
    options = [
        click.option("--asset", required=True, help="Asset address (with optional @chain)."),
        click.option("--amount", type=int, required=True),
        click.option("--nonce", type=int, help="Override the on-chain nonce."),
        click.option("--target", help="Target address (hex). Defaults to the signer."),
    ]
    for option in reversed(options):
        f = option(f)
    return f


def _build_manager(cli_ctx: CLIContext, signer) -> WithdrawalManager:
    return WithdrawalManager(
        default_user=cli_ctx.load_user(),
        ape_account=signer,
        clearing_engine=cli_ctx.clearing_engine_client(),
    )


@withdraw.command("init", cls=ConnectedProviderCommand)
@account_option()
@_withdrawal_options
@pass_cli_context
def _init(cli_ctx: CLIContext, account, asset: str, amount: int, nonce: int | None, target: str | None):
    """Initialize a withdrawal on the clearing engine."""
    manager = _build_manager(cli_ctx, account)
    info = asyncio.run(
        manager.init_withdrawal(
            asset=asset, amount=amount, nonce=nonce, target=target, then_execute=False
        )
    )
    click.echo(f"Withdrawal initialized. Nonce: {info.nonce}")


@withdraw.command("execute", cls=ConnectedProviderCommand)
@account_option()
@_withdrawal_options
@click.option("--poll-interval", type=float, default=2.0, show_default=True)
@click.option("--poll-timeout", type=float, default=60.0, show_default=True)
@pass_cli_context
def _execute(
    cli_ctx: CLIContext,
    account,
    asset: str,
    amount: int,
    nonce: int | None,
    target: str | None,
    poll_interval: float,
    poll_timeout: float,
):
    """Initialize and execute a withdrawal on-chain."""
    manager = _build_manager(cli_ctx, account)
    info = asyncio.run(
        manager.init_withdrawal(
            asset=asset,
            amount=amount,
            nonce=nonce,
            target=target,
            then_execute=True,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )
    )
    click.echo(f"Withdrawal executed. Nonce: {info.nonce}")


@withdraw.command("cancel")
@click.option("--asset", "asset_address", required=True, help="Asset address.")
@click.option("--nonce", type=int, required=True)
@pass_cli_context
def _cancel(cli_ctx: CLIContext, asset_address: str, nonce: int):
    """Cancel a queued withdrawal."""
    user = cli_ctx.load_user()
    request = CancelWithdrawalRequest.create_signed(
        signer=user, asset_address=asset_address, nonce=nonce
    )
    client = cli_ctx.clearing_engine_client()
    asyncio.run(client.withdrawals.cancel(request))
    click.echo("Withdrawal cancelled.")


@withdraw.command("list")
@click.option("--user", "user_pubkey", help="Public key. Defaults to the active account's.")
@pass_cli_context
def _list(cli_ctx: CLIContext, user_pubkey: str | None):
    """List queued withdrawals."""
    pubkey = user_pubkey or cli_ctx.load_user().public_key
    client = cli_ctx.clearing_engine_client()
    queued = asyncio.run(client.withdrawals.get_queued(pubkey))
    if not queued:
        click.echo("No queued withdrawals.")
        return

    for wd in queued:
        click.echo(wd.model_dump_json(indent=2))


@withdraw.command("signatures")
@click.option("--user", "user_pubkey", help="Public key. Defaults to the active account's.")
@pass_cli_context
def _signatures(cli_ctx: CLIContext, user_pubkey: str | None):
    """Fetch CE signatures for completed withdrawals."""
    pubkey = user_pubkey or cli_ctx.load_user().public_key
    client = cli_ctx.clearing_engine_client()
    result = asyncio.run(client.withdrawals.get_signatures(pubkey))
    click.echo(json.dumps(result, indent=2, default=str))
