import asyncio
import json
from typing import Any, cast

import click

from tplus._cli._context import (
    CLIContext,
    market_data_url_option,
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
@pass_cli_context
def _list(cli_ctx: CLIContext, output_format: str, no_pager: bool):
    """List all markets."""
    client = cli_ctx.orderbook_client()
    response = cast("list[dict[str, Any]]", asyncio.run(client._request("GET", "/markets")))
    if output_format == "raw":
        click.echo(json.dumps(response, indent=2, default=str))
        return

    records = []
    for market in response or []:
        fee_schedule = market.get("fee_schedule") or {}
        records.append(
            {
                "asset_id": market.get("asset_id"),
                "price_decimals": market.get("book_price_decimals"),
                "quantity_decimals": market.get("book_quantity_decimals"),
                "max_leverage": market.get("max_leverage"),
                "isolated_only": market.get("isolated_only"),
                "tick_size": market.get("tick_size"),
                "min_order_size": market.get("min_order_size"),
                "fee_account": fee_schedule.get("fee_account"),
                "fee_tiers": (
                    f"{len(fee_schedule.get('global') or [])} global / "
                    f"{len(fee_schedule.get('per_asset') or [])} per-asset"
                    if fee_schedule
                    else None
                ),
            }
        )
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
@pass_cli_context
def _klines(
    cli_ctx: CLIContext,
    output_format: str,
    no_pager: bool,
    asset_id: str,
    page: int | None,
    limit: int | None,
    end_timestamp_ns: int | None,
):
    """Get candlestick data for ASSET_ID."""
    from tplus.model.asset_identifier import AssetIdentifier

    client = cli_ctx.market_data_client()
    klines = asyncio.run(
        client.get_klines(
            AssetIdentifier(asset_id), page=page, limit=limit, end_timestamp_ns=end_timestamp_ns
        )
    )
    if output_format == "raw":
        echo_with_pager(
            [kline.model_dump_json() for kline in klines],
            no_pager=no_pager,
        )
        return

    render([kline.model_dump() for kline in klines], output_format, no_pager=no_pager)
