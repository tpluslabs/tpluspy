import asyncio
import json

import click

from tplus._cli._context import CLIContext, pass_cli_context


@click.command("balance")
@click.option("--asset-id", "asset_id", help="Filter inventory to a single asset.")
@pass_cli_context
def balance(cli_ctx: CLIContext, asset_id: str | None):
    """Show user inventory."""
    client = cli_ctx.orderbook_client()
    inventory = asyncio.run(client.get_user_inventory())

    if asset_id:
        inventory = inventory.get(asset_id) or inventory.get(str(asset_id)) or {}

    if not inventory:
        click.echo("No inventory.")
        return

    click.echo(json.dumps(inventory, indent=2, default=str))
