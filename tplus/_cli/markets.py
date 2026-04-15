import asyncio
import json

import click

from tplus._cli._context import CLIContext, pass_cli_context


@click.group()
def markets():
    """Manage T+ markets."""


@markets.command("create")
@click.argument("asset_id")
@pass_cli_context
def _create(cli_ctx: CLIContext, asset_id: str):
    """Create a market for ASSET_ID."""
    client = cli_ctx.orderbook_client()
    response = asyncio.run(client.create_market(asset_id))
    click.echo(json.dumps(response, indent=2, default=str))


@markets.command("get")
@click.argument("asset_id")
@pass_cli_context
def _get(cli_ctx: CLIContext, asset_id: str):
    """Get the market details for ASSET_ID."""
    from tplus.model.asset_identifier import AssetIdentifier

    client = cli_ctx.orderbook_client()
    market = asyncio.run(client.get_market(AssetIdentifier(asset_id)))
    click.echo(market.model_dump_json(indent=2))


@markets.command("list")
@pass_cli_context
def _list(cli_ctx: CLIContext):
    """List all markets."""
    client = cli_ctx.orderbook_client()
    response = asyncio.run(client._request("GET", "/markets"))
    click.echo(json.dumps(response, indent=2, default=str))


@markets.command("depth")
@click.argument("asset_id")
@pass_cli_context
def _depth(cli_ctx: CLIContext, asset_id: str):
    """Get the order book snapshot for ASSET_ID."""
    from tplus.model.asset_identifier import AssetIdentifier

    client = cli_ctx.orderbook_client()
    snapshot = asyncio.run(client.get_orderbook_snapshot(AssetIdentifier(asset_id)))
    click.echo(snapshot.model_dump_json(indent=2))


@markets.command("klines")
@click.argument("asset_id")
@click.option("--page", type=int)
@click.option("--limit", type=int)
@click.option("--end-timestamp-ns", "end_timestamp_ns", type=int)
@pass_cli_context
def _klines(
    cli_ctx: CLIContext,
    asset_id: str,
    page: int | None,
    limit: int | None,
    end_timestamp_ns: int | None,
):
    """Get candlestick data for ASSET_ID."""
    from tplus.model.asset_identifier import AssetIdentifier

    client = cli_ctx.orderbook_client()
    klines = asyncio.run(
        client.get_klines(
            AssetIdentifier(asset_id), page=page, limit=limit, end_timestamp_ns=end_timestamp_ns
        )
    )
    for kline in klines:
        click.echo(kline.model_dump_json())
