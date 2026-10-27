from decimal import Decimal

import pytest

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.batch_order import BatchCancelStatus
from tplus.model.order import OrderResponse, Side


@pytest.fixture(scope="session")
def book_order():
    return OrderResponse(
        order_id="order-1",
        base_asset=AssetIdentifier("200"),
        side=Side.BUY,
        limit_price=Decimal("100"),
        quantity=Decimal("5"),
        amount=None,
        max_sellable_amount=None,
        max_sellable_quantity=None,
        confirmed_filled_quantity=Decimal(0),
        pending_filled_quantity=Decimal(0),
        confirmed_filled_amount=Decimal(0),
        pending_filled_amount=Decimal(0),
        confirmed_trading_fees_amount=Decimal(0),
        pending_trading_fees_amount=Decimal(0),
        good_until_timestamp_ns=None,
        timestamp_ns=1_700_000_000_000_000_000,
        status="Open",
        trigger_above_price=None,
        trigger_below_price=None,
        last_update_timestamp_ns=None,
    )


@pytest.mark.anyio
async def test_get_order_looks_up_by_query(mock_client, book_order):
    client, request = mock_client
    request.return_value = book_order.model_dump(mode="json")

    order = await client.get_order("order-1")

    assert request.call_args.args[:2] == ("GET", "/orders/lookup")
    assert request.call_args.kwargs["params"] == {"order_id": "order-1"}
    assert order == book_order


@pytest.mark.anyio
async def test_cancel_orders_sends_one_batch(mock_client):
    client, request = mock_client
    request.return_value = {"status": "partial", "dispatched": 1, "failures": ["200"]}

    response = await client.cancel_orders(["order-1", "order-2"])

    assert request.call_args.args[:2] == ("DELETE", "/orders/cancel-batch")
    assert request.call_args.kwargs["json_data"] == {"order_ids": ["order-1", "order-2"]}
    assert (response.status, response.dispatched, response.failures) == (
        BatchCancelStatus.PARTIAL,
        1,
        ["200"],
    )
