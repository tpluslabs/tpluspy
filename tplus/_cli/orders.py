import asyncio
import json

import click

from tplus._cli._context import CLIContext, pass_cli_context


@click.group()
def orders():
    """Manage T+ orders."""


@orders.command("place")
@click.option("--asset", "asset_id", required=True, help="Asset identifier.")
@click.option(
    "--side",
    type=click.Choice(["buy", "sell"], case_sensitive=False),
    required=True,
)
@click.option(
    "--type",
    "order_type",
    type=click.Choice(["limit", "market"], case_sensitive=False),
    default="limit",
    show_default=True,
)
@click.option("--quantity", type=int, required=True, help="Base quantity (scaled int).")
@click.option("--price", type=int, help="Price (scaled int). Required for limit orders.")
@pass_cli_context
def _place(
    cli_ctx: CLIContext,
    asset_id: str,
    side: str,
    order_type: str,
    quantity: int,
    price: int | None,
):
    """Place a new order."""
    from tplus.model.asset_identifier import AssetIdentifier

    client = cli_ctx.orderbook_client()
    asset = AssetIdentifier(asset_id)

    if order_type == "limit":
        if price is None:
            raise click.UsageError("--price is required for limit orders.")

        response = asyncio.run(
            client.create_limit_order(
                quantity=quantity, price=price, side=side, asset_id=asset
            )
        )
    else:
        response = asyncio.run(
            client.create_market_order(side=side, base_quantity=quantity, asset_id=asset)
        )

    click.echo(response.model_dump_json(indent=2))


@orders.command("cancel")
@click.argument("order_id")
@click.option("--asset", "asset_id", required=True, help="Asset identifier.")
@pass_cli_context
def _cancel(cli_ctx: CLIContext, order_id: str, asset_id: str):
    """Cancel ORDER_ID."""
    from tplus.model.asset_identifier import AssetIdentifier

    client = cli_ctx.orderbook_client()
    response = asyncio.run(client.cancel_order(order_id, AssetIdentifier(asset_id)))
    click.echo(response.model_dump_json(indent=2))


@orders.command("replace")
@click.argument("order_id")
@click.option("--asset", "asset_id", required=True, help="Asset identifier.")
@click.option("--quantity", type=int, help="New base quantity.")
@click.option("--price", type=int, help="New price.")
@pass_cli_context
def _replace(
    cli_ctx: CLIContext,
    order_id: str,
    asset_id: str,
    quantity: int | None,
    price: int | None,
):
    """Replace ORDER_ID with new parameters."""
    if quantity is None and price is None:
        raise click.UsageError("Pass --quantity and/or --price.")

    from tplus.model.asset_identifier import AssetIdentifier

    client = cli_ctx.orderbook_client()
    response = asyncio.run(
        client.replace_order(
            original_order_id=order_id,
            asset_id=AssetIdentifier(asset_id),
            new_quantity=quantity,
            new_price=price,
        )
    )
    click.echo(response.model_dump_json(indent=2))


@orders.command("transfer")
@click.option("--source", "source_index", type=int, required=True, help="Source sub-account index.")
@click.option("--target", "target_index", type=int, required=True, help="Target sub-account index.")
@click.option("--asset", "asset_id", required=True, help="Asset identifier.")
@click.option("--amount", type=int, required=True)
@pass_cli_context
def _transfer(
    cli_ctx: CLIContext, source_index: int, target_index: int, asset_id: str, amount: int
):
    """Transfer between sub-accounts."""
    from tplus.model.asset_identifier import AssetIdentifier

    client = cli_ctx.orderbook_client()
    response = asyncio.run(
        client.request_transfer_to_subaccount(
            source_index=source_index,
            target_index=target_index,
            transfer_asset=AssetIdentifier(asset_id),
            transfer_amount=amount,
        )
    )
    click.echo(json.dumps(response, indent=2, default=str))


@orders.command("close")
@click.option("--account", "account_index", type=int, required=True, help="Sub-account index.")
@click.option("--asset", "asset_id", required=True, help="Transfer asset identifier.")
@pass_cli_context
def _close(cli_ctx: CLIContext, account_index: int, asset_id: str):
    """Close a position on a sub-account."""
    client = cli_ctx.orderbook_client()
    response = asyncio.run(client.request_close_position(account_index, asset_id))
    click.echo(json.dumps(response, indent=2, default=str))


@orders.command("list")
@click.option("--asset", "asset_id", help="Filter by asset identifier.")
@click.option("--open-only", is_flag=True, help="Only show open orders.")
@pass_cli_context
def _list(cli_ctx: CLIContext, asset_id: str | None, open_only: bool):
    """List orders for the current account."""
    from tplus.model.asset_identifier import AssetIdentifier

    client = cli_ctx.orderbook_client()
    if asset_id:
        result = asyncio.run(
            client.get_user_orders_for_book(
                AssetIdentifier(asset_id), open_only=open_only or None
            )
        )
    else:
        if open_only:
            raise click.UsageError("--open-only requires --asset.")
        result, _ = asyncio.run(client.get_user_orders())

    if not result:
        click.echo("No orders found.")
        return

    for order in result:
        click.echo(order.model_dump_json(indent=2))
