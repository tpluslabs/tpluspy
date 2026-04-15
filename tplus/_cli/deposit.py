import asyncio

import click
from ape.cli import ConnectedProviderCommand, account_option

from tplus._cli._context import CLIContext, pass_cli_context
from tplus.evm.managers.deposit import DepositManager


@click.command("deposit", cls=ConnectedProviderCommand)
@account_option()
@click.argument("token")
@click.option("--amount", type=int, required=True)
@click.option("--wait/--no-wait", default=False, help="Wait for CE to ingest the deposit.")
@pass_cli_context
def deposit(cli_ctx: CLIContext, account, token: str, amount: int, wait: bool):
    """Deposit AMOUNT of TOKEN into the vault."""
    try:
        ce = cli_ctx.clearing_engine_client()
    except click.UsageError:
        ce = None

    manager = DepositManager(
        account=account,
        default_user=cli_ctx.load_user(),
        clearing_engine=ce,
    )
    asyncio.run(manager.deposit(token, amount, wait=wait))
    click.echo(f"Deposited {amount} of {token}.")
