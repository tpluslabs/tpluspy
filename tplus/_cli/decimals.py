import asyncio
import json

import click

from tplus._cli._context import CLIContext, pass_cli_context


@click.group()
def decimals():
    """Query / refresh CE decimal cache."""


@decimals.command("get")
@click.argument("addresses", nargs=-1, required=True)
@pass_cli_context
def _get(cli_ctx: CLIContext, addresses: tuple[str, ...]):
    """Get cached decimals for ADDRESSES."""
    client = cli_ctx.clearing_engine_client()
    result = asyncio.run(client.decimals.get(list(addresses)))
    click.echo(json.dumps(result, indent=2, default=str))


@decimals.command("update")
@click.argument("addresses", nargs=-1, required=True)
@pass_cli_context
def _update(cli_ctx: CLIContext, addresses: tuple[str, ...]):
    """Request CE refresh decimals for ADDRESSES."""
    client = cli_ctx.clearing_engine_client()
    asyncio.run(client.decimals.update(list(addresses)))
    click.echo("Decimals update requested.")
