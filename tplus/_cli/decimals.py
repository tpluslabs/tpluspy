import asyncio
import json

import click

from tplus._cli._context import CLIContext, orderbook_url_option, pass_cli_context
from tplus.cli_tools import ignore_ssl_option


@click.group()
def decimals():
    """Query / refresh OMS decimal cache."""


@decimals.command("get")
@orderbook_url_option()
@ignore_ssl_option()
@click.argument("addresses", nargs=-1, required=True)
@pass_cli_context
def _get(cli_ctx: CLIContext, addresses: tuple[str, ...]):
    """Get cached decimals for ADDRESSES."""
    client = cli_ctx.orderbook_client(anonymous=True)
    result = asyncio.run(client.assets.get_asset_decimals(list(addresses)))
    click.echo(json.dumps(result, indent=2, default=str))


@decimals.command("update")
@orderbook_url_option()
@ignore_ssl_option()
@click.argument("addresses", nargs=-1, required=True)
@pass_cli_context
def _update(cli_ctx: CLIContext, addresses: tuple[str, ...]):
    """Request OMS refresh decimals for ADDRESSES."""
    client = cli_ctx.orderbook_client(anonymous=True)
    asyncio.run(client.assets.update_asset_decimals(list(addresses)))
    click.echo("Decimals update requested.")
