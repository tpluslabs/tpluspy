import click

from tplus._cli._context import CLIContext, pass_cli_context
from tplus._cli.accounts import accounts
from tplus._cli.balance import balance
from tplus._cli.decimals import decimals
from tplus._cli.markets import markets
from tplus._cli.orders import orders
from tplus._cli.sign import sign
from tplus._cli.stream import stream
from tplus._cli.trades import trades


@click.group()
@click.option(
    "--orderbook-base-url",
    envvar="TPLUS_ORDERBOOK_BASE_URL",
    help="T+ orderbook service base URL.",
)
@click.option(
    "--clearing-base-url",
    envvar="TPLUS_CLEARING_BASE_URL",
    help="T+ clearing engine base URL.",
)
@click.option("--account", envvar="TPLUS_ACCOUNT", help="Default account alias.")
@click.version_option(package_name="tpluspy")
@pass_cli_context
def cli(
    cli_ctx: CLIContext,
    orderbook_base_url: str | None,
    clearing_base_url: str | None,
    account: str | None,
):
    """T+ command line interface."""
    cli_ctx.orderbook_base_url = orderbook_base_url
    cli_ctx.clearing_base_url = clearing_base_url
    cli_ctx.account = account


cli.add_command(accounts)
cli.add_command(balance)
cli.add_command(decimals)
cli.add_command(markets)
cli.add_command(orders)
cli.add_command(sign)
cli.add_command(stream)
cli.add_command(trades)

try:
    from tplus._cli.assets import assets
    from tplus._cli.deposit import deposit
    from tplus._cli.settle import settle
    from tplus._cli.vault import vault
    from tplus._cli.withdraw import withdraw

    cli.add_command(assets)
    cli.add_command(deposit)
    cli.add_command(settle)
    cli.add_command(vault)
    cli.add_command(withdraw)
    cli.add_command(withdraw, name="wd")
except ImportError:
    pass
