import asyncio
import importlib.util
import json
from typing import TYPE_CHECKING

import click

from tplus._cli._context import (
    CLIContext,
    orderbook_url_option,
    pass_cli_context,
    tplus_account_option,
)
from tplus.cli_tools import (
    echo_with_pager,
    ignore_ssl_option,
    no_pager_option,
    output_format_option,
    render,
)

if TYPE_CHECKING:
    from tplus.evm.managers.withdraw import WithdrawalManager


_EVM_AVAILABLE = importlib.util.find_spec("ape") is not None


@click.group()
def withdraw():
    """Withdraw T+ assets."""


@withdraw.command("cancel")
@orderbook_url_option()
@ignore_ssl_option()
@tplus_account_option()
@click.option("--asset", "asset_address", required=True, help="Asset address.")
@click.option("--nonce", type=int, required=True)
@pass_cli_context
def _cancel(cli_ctx: CLIContext, asset_address: str, nonce: int):
    """Cancel a queued withdrawal."""
    from tplus.model.withdrawal import CancelWithdrawalRequest

    user = cli_ctx.load_user()
    request = CancelWithdrawalRequest.create_signed(
        signer=user, asset_address=asset_address, nonce=nonce
    )
    client = cli_ctx.withdrawal_client()
    asyncio.run(client.cancel_withdrawal(request))
    click.echo("Withdrawal cancelled.")


@withdraw.command("list")
@orderbook_url_option()
@ignore_ssl_option()
@tplus_account_option()
@output_format_option()
@no_pager_option()
@click.option("--user", "user_pubkey", help="Public key. Defaults to the active account's.")
@pass_cli_context
def _list(cli_ctx: CLIContext, output_format: str, no_pager: bool, user_pubkey: str | None):
    """List queued withdrawals."""
    pubkey = user_pubkey or cli_ctx.load_user().public_key
    client = cli_ctx.withdrawal_client()
    queued = asyncio.run(client.get_queued_withdrawals(pubkey))
    if not queued:
        click.echo("No queued withdrawals.")
        return

    if output_format == "raw":
        echo_with_pager(
            [json.dumps(wd, indent=2, default=str) for wd in queued],
            no_pager=no_pager,
        )
        return

    records = []
    for wd in queued:
        raw_status = wd.get("status")
        status = raw_status if isinstance(raw_status, dict) else {}
        records.append(
            {
                "asset": wd.get("asset"),
                "amount": wd.get("amount"),
                "nonce": wd.get("nonce"),
                "target": wd.get("target"),
                "tplus_user": wd.get("tplus_user"),
                "status": status.get("type", raw_status),
            }
        )
    render(records, output_format, no_pager=no_pager)


@withdraw.command("signatures")
@orderbook_url_option()
@ignore_ssl_option()
@tplus_account_option()
@click.option("--user", "user_pubkey", help="Public key. Defaults to the active account's.")
@click.option("--nonce", type=int, help="Only show approvals for this nonce.")
@pass_cli_context
def _signatures(cli_ctx: CLIContext, user_pubkey: str | None, nonce: int | None):
    """Show approval signatures for approved withdrawals."""
    pubkey = user_pubkey or cli_ctx.load_user().public_key
    client = cli_ctx.withdrawal_client()
    queued = asyncio.run(client.get_queued_withdrawals(pubkey))

    result = {}
    for wd in queued:
        if nonce is not None and wd.get("nonce") != nonce:
            continue
        status = wd.get("status")
        if not isinstance(status, dict) or status.get("type") != "approved":
            continue
        result[wd.get("nonce")] = status.get("approvals")

    click.echo(json.dumps(result, indent=2, default=str))


if _EVM_AVAILABLE:
    from ape.cli import ConnectedProviderCommand, account_option

    from tplus.cli_tools import tplus_network_option

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

    def _build_manager(cli_ctx: CLIContext, signer) -> "WithdrawalManager":
        from tplus.evm.managers.withdraw import WithdrawalManager

        return WithdrawalManager(
            default_user=cli_ctx.load_user(),
            ape_account=signer,
            withdrawal_client=cli_ctx.withdrawal_client(),
        )

    @withdraw.command("init", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @orderbook_url_option()
    @ignore_ssl_option()
    @tplus_account_option()
    @account_option()
    @_withdrawal_options
    @pass_cli_context
    def _init(
        cli_ctx: CLIContext,
        account,
        asset: str,
        amount: int,
        nonce: int | None,
        target: str | None,
    ):
        """Initialize a withdrawal on the clearing engine."""
        from tplus.model.asset_identifier import ChainAddress

        manager = _build_manager(cli_ctx, account)
        info = asyncio.run(
            manager.init_withdrawal(
                asset=ChainAddress.from_str(asset),
                amount=amount,
                nonce=nonce,
                target=target,
                then_execute=False,
            )
        )
        click.echo(f"Withdrawal initialized. Nonce: {info.nonce}")

    @withdraw.command("execute", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @orderbook_url_option()
    @ignore_ssl_option()
    @tplus_account_option()
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
        from tplus.model.asset_identifier import ChainAddress

        manager = _build_manager(cli_ctx, account)
        info = asyncio.run(
            manager.init_withdrawal(
                asset=ChainAddress.from_str(asset),
                amount=amount,
                nonce=nonce,
                target=target,
                then_execute=True,
                poll_interval=poll_interval,
                poll_timeout=poll_timeout,
            )
        )
        click.echo(f"Withdrawal executed. Nonce: {info.nonce}")
