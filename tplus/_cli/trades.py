import asyncio

import click

from tplus._cli._context import CLIContext, pass_cli_context


@click.group()
def trades():
    """View T+ trade history."""


@trades.command("list")
@click.option("--asset", "asset_id", help="Filter to a single asset.")
@pass_cli_context
def _list(cli_ctx: CLIContext, asset_id: str | None):
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

    for trade in result:
        click.echo(trade.model_dump_json(indent=2))
