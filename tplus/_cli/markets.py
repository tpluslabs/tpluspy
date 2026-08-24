import asyncio
import json

import click

from tplus._cli._context import (
    CLIContext,
    market_data_url_option,
    orderbook_url_option,
    pass_cli_context,
    tplus_account_option,
)
from tplus.asset_metadata import asset_metadata_dict
from tplus.cli_tools import (
    echo_with_pager,
    ignore_ssl_option,
    no_pager_option,
    output_format_option,
    render,
)
from tplus.model.market import MarketResponse


async def _collect_markets(
    client, page_number: int | None, limit: int | None
) -> list[MarketResponse]:
    """The requested page, or every page when the caller did not pick one."""
    page = await client.get_markets(page=page_number, limit=limit)
    if page_number is not None:
        return page.markets

    markets = list(page.markets)
    while page.next_page is not None:
        page = await client.get_markets(page=page.next_page, limit=limit)
        markets.extend(page.markets)

    return markets


@click.group()
def markets():
    """Manage T+ markets."""


@markets.command("create")
@orderbook_url_option()
@ignore_ssl_option()
@tplus_account_option()
@click.argument("asset_id")
@pass_cli_context
def _create(cli_ctx: CLIContext, asset_id: str):
    """Create a market for ASSET_ID."""
    client = cli_ctx.orderbook_client()
    response = asyncio.run(client.create_market(asset_id))
    click.echo(json.dumps(response, indent=2, default=str))


@markets.command("get")
@orderbook_url_option()
@ignore_ssl_option()
@tplus_account_option()
@click.argument("asset_id")
@pass_cli_context
def _get(cli_ctx: CLIContext, asset_id: str):
    """Get the market details for ASSET_ID."""
    from tplus.model.asset_identifier import AssetIdentifier

    client = cli_ctx.orderbook_client()
    market = asyncio.run(client.get_market(AssetIdentifier(asset_id)))
    click.echo(market.model_dump_json(indent=2))


@markets.command("list")
@orderbook_url_option()
@ignore_ssl_option()
@tplus_account_option()
@output_format_option()
@no_pager_option()
@click.option("--page", "page_number", type=int)
@click.option("--limit", type=int)
@pass_cli_context
def _list(
    cli_ctx: CLIContext,
    output_format: str,
    no_pager: bool,
    page_number: int | None,
    limit: int | None,
):
    """List all markets, following pagination unless `--page` picks one."""
    client = cli_ctx.orderbook_client()
    markets = asyncio.run(_collect_markets(client, page_number, limit))
    if output_format == "raw":
        raw = [market.model_dump(by_alias=True) for market in markets]
        click.echo(json.dumps(raw, indent=2, default=str))
        return

    records = []
    for market in markets:
        fee_schedule = market.fee_schedule
        asset_metadata = asset_metadata_dict(str(market.asset_id)) or {}
        records.append(
            {
                "asset_id": str(market.asset_id),
                "symbol": asset_metadata.get("symbol"),
                "asset_class": asset_metadata.get("asset_class"),
                "representations": asset_metadata.get("representations"),
                "price_decimals": market.book_price_decimals,
                "quantity_decimals": market.book_quantity_decimals,
                "max_leverage": market.max_leverage,
                "isolated_only": market.isolated_only,
                "tick_size": market.tick_size,
                "min_order_size": market.min_order_size,
                "fee_account": fee_schedule.fee_account if fee_schedule else None,
                "fee_tiers": (
                    f"{len(fee_schedule.global_)} global / {len(fee_schedule.per_asset)} per-asset"
                    if fee_schedule
                    else None
                ),
            }
        )
    render(records, output_format, no_pager=no_pager)


@markets.command("symbol-map")
@orderbook_url_option()
@ignore_ssl_option()
@tplus_account_option()
@output_format_option()
@no_pager_option()
@pass_cli_context
def _symbol_map(cli_ctx: CLIContext, output_format: str, no_pager: bool):
    """Show the canonical asset table served by the OMS."""
    client = cli_ctx.orderbook_client()
    symbol_map = asyncio.run(client.get_markets(include_symbol_map=True)).symbol_map or {}
    if output_format == "raw":
        raw = {str(index): asset.model_dump() for index, asset in symbol_map.items()}
        click.echo(json.dumps(raw, indent=2))
        return

    records = [
        {
            "index": index,
            "symbol": asset.symbol,
            "name": asset.name,
            "asset_class": asset.asset_class,
            "representations": ", ".join(asset.representations),
        }
        for index, asset in sorted(symbol_map.items())
    ]
    render(records, output_format, no_pager=no_pager)


@markets.command("depth")
@market_data_url_option()
@ignore_ssl_option()
@click.argument("asset_id")
@pass_cli_context
def _depth(cli_ctx: CLIContext, asset_id: str):
    """Get the order book snapshot for ASSET_ID."""
    from tplus.model.asset_identifier import AssetIdentifier

    client = cli_ctx.market_data_client()
    snapshot = asyncio.run(client.get_orderbook_snapshot(AssetIdentifier(asset_id)))
    click.echo(snapshot.model_dump_json(indent=2))


@markets.command("klines")
@market_data_url_option()
@ignore_ssl_option()
@output_format_option()
@no_pager_option()
@click.argument("asset_id")
@click.option("--page", type=int)
@click.option("--limit", type=int)
@click.option("--end-timestamp-ns", "end_timestamp_ns", type=int)
@click.option("--interval", help="Bucket width, e.g. 1, 5m, 4h, 1D, 1W or 1M (a month).")
@pass_cli_context
def _klines(
    cli_ctx: CLIContext,
    output_format: str,
    no_pager: bool,
    asset_id: str,
    page: int | None,
    limit: int | None,
    end_timestamp_ns: int | None,
    interval: str | None,
):
    """Get candlestick data for ASSET_ID."""
    from tplus.model.asset_identifier import AssetIdentifier

    client = cli_ctx.market_data_client()
    klines = asyncio.run(
        client.get_klines(
            AssetIdentifier(asset_id),
            page=page,
            limit=limit,
            end_timestamp_ns=end_timestamp_ns,
            interval=interval,
        )
    )
    if output_format == "raw":
        echo_with_pager(
            [kline.model_dump_json() for kline in klines.items],
            no_pager=no_pager,
        )
        return

    render([kline.model_dump() for kline in klines.items], output_format, no_pager=no_pager)
