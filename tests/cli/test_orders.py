from decimal import Decimal

from tplus._cli import cli
from tplus.client.orderbook import OrderBookClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.order import OperationStatus, OrderOperationResponse, OrderResponse, Side

from .conftest import PRIVATE_KEY_HEX

ASSET_ID = "1"
ORDER_ID = "order-abc"
ORDERBOOK_URL = "http://orderbook.test"


def _stub_response(order_id: str = ORDER_ID) -> OrderOperationResponse:
    return OrderOperationResponse(order_id=order_id, status=OperationStatus.RECEIVED)


def _stub_order(order_id: str = ORDER_ID) -> OrderResponse:
    zero = Decimal("0")
    return OrderResponse(
        order_id=order_id,
        base_asset=AssetIdentifier(ASSET_ID),
        side=Side.BUY,
        limit_price=Decimal("100"),
        quantity=Decimal("5"),
        amount=None,
        max_sellable_amount=None,
        max_sellable_quantity=None,
        confirmed_filled_quantity=zero,
        pending_filled_quantity=zero,
        confirmed_filled_amount=zero,
        pending_filled_amount=zero,
        confirmed_trading_fees_amount=zero,
        pending_trading_fees_amount=zero,
        good_until_timestamp_ns=None,
        timestamp_ns=0,
        status="Open",
        trigger_above_price=None,
        trigger_below_price=None,
        last_update_timestamp_ns=None,
    )


def test_orders_place_list_cancel(runner, user_dir, monkeypatch):
    runner.invoke(cli, ["accounts", "add", "trader", "--private-key", PRIVATE_KEY_HEX])
    monkeypatch.setenv("TPLUS_ACCOUNT", "trader")
    monkeypatch.setenv("TPLUS_ORDERBOOK_BASE_URL", ORDERBOOK_URL)

    captured: dict = {}

    async def fake_create_limit(self, quantity, price, side, asset_id):
        captured["place"] = {
            "quantity": quantity,
            "price": price,
            "side": side,
            "asset_id": str(asset_id),
        }
        return _stub_response()

    async def fake_get_user_orders_for_book(self, asset_id, open_only=None):
        captured["list"] = {"asset_id": str(asset_id), "open_only": open_only}
        return [_stub_order()]

    async def fake_cancel(self, order_id, asset_id):
        captured["cancel"] = {"order_id": order_id, "asset_id": str(asset_id)}
        return _stub_response(order_id)

    monkeypatch.setattr(OrderBookClient, "create_limit_order", fake_create_limit)
    monkeypatch.setattr(OrderBookClient, "get_user_orders_for_book", fake_get_user_orders_for_book)
    monkeypatch.setattr(OrderBookClient, "cancel_order", fake_cancel)

    place = runner.invoke(
        cli,
        [
            "orders",
            "place",
            "--asset",
            ASSET_ID,
            "--side",
            "buy",
            "--type",
            "limit",
            "--quantity",
            "5",
            "--price",
            "100",
        ],
    )
    assert place.exit_code == 0, place.output
    assert ORDER_ID in place.output
    assert captured["place"] == {
        "quantity": 5,
        "price": 100,
        "side": "buy",
        "asset_id": ASSET_ID,
    }

    listed = runner.invoke(cli, ["orders", "list", "--asset", ASSET_ID, "--open-only"])
    assert listed.exit_code == 0, listed.output
    assert ORDER_ID in listed.output
    assert captured["list"] == {"asset_id": ASSET_ID, "open_only": True}

    cancel = runner.invoke(cli, ["orders", "cancel", ORDER_ID, "--asset", ASSET_ID])
    assert cancel.exit_code == 0, cancel.output
    assert ORDER_ID in cancel.output
    assert captured["cancel"] == {"order_id": ORDER_ID, "asset_id": ASSET_ID}
