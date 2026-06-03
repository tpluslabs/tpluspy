import asyncio

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


@click.group()
def trades():
    """View T+ trade history."""


@trades.command("list")
@orderbook_url_option()
@ignore_ssl_option()
@tplus_account_option()
@output_format_option()
@no_pager_option()
@click.option("--asset", "asset_id", help="Filter to a single asset.")
@pass_cli_context
def _list(cli_ctx: CLIContext, output_format: str, no_pager: bool, asset_id: str | None):
    """List user trades."""
    from tplus.model.asset_identifier import AssetIdentifier

    client = cli_ctx.orderbook_client()
    if asset_id:
        result = asyncio.run(client.get_user_trades_for_asset(AssetIdentifier(asset_id)))
    else:
        result = asyncio.run(client.get_user_trades())

    if not result:
        click.echo("No trades.")
        return

    if output_format == "raw":
        echo_with_pager(
            [trade.model_dump_json(indent=2) for trade in result],
            no_pager=no_pager,
        )
        return

    render([trade.model_dump() for trade in result], output_format, no_pager=no_pager)
