import asyncio

import click

from tplus._cli._context import CLIContext, pass_cli_context


@click.group()
def stream():
    """Stream real-time T+ data over WebSocket."""


def _run_stream(aiter_factory):
    async def _runner():
        async for event in aiter_factory():
            try:
                click.echo(event.model_dump_json())
            except AttributeError:
                click.echo(str(event))

    try:
        asyncio.run(_runner())
    except KeyboardInterrupt:
        pass


@stream.command("orders")
@pass_cli_context
def _orders(cli_ctx: CLIContext):
    """Stream order events."""
    client = cli_ctx.orderbook_client()
    _run_stream(client.stream_orders)


@stream.command("trades")
@pass_cli_context
def _trades(cli_ctx: CLIContext):
    """Stream finalized trades."""
    client = cli_ctx.orderbook_client()
    _run_stream(client.stream_finalized_trades)


@stream.command("depth")
@click.argument("asset_id")
@pass_cli_context
def _depth(cli_ctx: CLIContext, asset_id: str):
    """Stream order book diffs for ASSET_ID."""
    from tplus.model.asset_identifier import AssetIdentifier

    client = cli_ctx.orderbook_client()
    asset = AssetIdentifier(asset_id)
    _run_stream(lambda: client.stream_depth(asset))


@stream.command("klines")
@click.argument("asset_id")
@pass_cli_context
def _klines(cli_ctx: CLIContext, asset_id: str):
    """Stream kline updates for ASSET_ID."""
    from tplus.model.asset_identifier import AssetIdentifier

    client = cli_ctx.orderbook_client()
    asset = AssetIdentifier(asset_id)
    _run_stream(lambda: client.stream_klines(asset))


@stream.command("user-trades")
@click.option("--user", "user_id", help="Override the user. Defaults to the active account.")
@pass_cli_context
def _user_trades(cli_ctx: CLIContext, user_id: str | None):
    """Stream user trade events."""
    client = cli_ctx.orderbook_client()
    _run_stream(lambda: client.stream_user_trade_events(user_id=user_id))
