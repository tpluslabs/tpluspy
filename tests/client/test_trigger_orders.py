from typing import Any

import pytest

from tplus.client.orderbook import OrderBookClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.market import Market
from tplus.model.order_trigger import OrderTrigger, TriggerAbove, TriggerBelow
from tplus.utils.user import User


class _CapturingClient(OrderBookClient):
    def __init__(self, user: User, base_url: str = "http://example.com"):
        super().__init__(default_user=user, base_url=base_url)
        self.captured: dict[str, Any] | None = None

    def _require_captured(self) -> dict[str, Any]:
        assert self.captured is not None
        return self.captured

    async def get_market(self, asset_id: AssetIdentifier) -> Market:  # type: ignore[override]
        return Market(asset_id=asset_id, book_price_decimals=2, book_quantity_decimals=3)

    async def _request(self, method, endpoint, json_data=None, params=None):  # type: ignore[override]
        self.captured = json_data
        return {"order_id": "stub", "status": "Received"}


def _trigger_above(price: int = 100_00) -> OrderTrigger:
    return OrderTrigger(parent_order_id=None, trigger=TriggerAbove(price=price))


def _trigger_below(price: int = 90_00, parent_id: str | None = "parent-123") -> OrderTrigger:
    return OrderTrigger(parent_order_id=parent_id, trigger=TriggerBelow(price=price))


@pytest.mark.anyio
async def test_create_limit_order_threads_trigger():
    client = _CapturingClient(user=User())

    await client.create_limit_order(
        quantity=10,
        price=100_00,
        side="Buy",
        asset_id=AssetIdentifier("200"),
        trigger=_trigger_above(),
    )

    assert client._require_captured()["order"]["trigger"] == {
        "parent_order_id": None,
        "condition": {"PriceAbove": {"price": 100_00}},
    }


@pytest.mark.anyio
async def test_create_limit_order_without_trigger_serialises_null():
    client = _CapturingClient(user=User())

    await client.create_limit_order(
        quantity=10,
        price=100_00,
        side="Buy",
        asset_id=AssetIdentifier("200"),
    )

    assert client._require_captured()["order"]["trigger"] is None


@pytest.mark.anyio
async def test_create_market_order_threads_trigger():
    client = _CapturingClient(user=User())

    await client.create_market_order(
        side="Sell",
        base_quantity=5,
        asset_id=AssetIdentifier("200"),
        trigger=_trigger_below(),
    )

    assert client._require_captured()["order"]["trigger"] == {
        "parent_order_id": "parent-123",
        "condition": {"PriceBelow": {"price": 90_00}},
    }


@pytest.mark.anyio
async def test_create_market_order_without_trigger_serialises_null():
    client = _CapturingClient(user=User())

    await client.create_market_order(
        side="Sell",
        base_quantity=5,
        asset_id=AssetIdentifier("200"),
    )

    assert client._require_captured()["order"]["trigger"] is None


@pytest.mark.anyio
async def test_create_market_order_threads_max_sellable_amount():
    client = _CapturingClient(user=User())

    await client.create_market_order(
        side="Buy",
        base_quantity=5,
        asset_id=AssetIdentifier("200"),
        max_sellable_amount=1_000_000,
    )

    base_asset = client._require_captured()["order"]["details"]["Market"]["quantity"]["BaseAsset"]
    assert base_asset == {"quantity": 5, "max_sellable_amount": 1_000_000}


@pytest.mark.anyio
async def test_create_market_order_threads_max_sellable_quantity():
    client = _CapturingClient(user=User())

    await client.create_market_order(
        side="Sell",
        quote_quantity=10_000,
        asset_id=AssetIdentifier("200"),
        max_sellable_quantity=50,
    )

    quote_asset = client._require_captured()["order"]["details"]["Market"]["quantity"]["QuoteAsset"]
    assert quote_asset == {"quantity": 10_000, "max_sellable_quantity": 50}


@pytest.mark.anyio
async def test_create_market_order_rejects_mismatched_max_sellable():
    client = _CapturingClient(user=User())

    with pytest.raises(ValueError, match="max_sellable_quantity requires quote_quantity"):
        await client.create_market_order(
            side="Buy",
            base_quantity=5,
            asset_id=AssetIdentifier("200"),
            max_sellable_quantity=50,
        )

    with pytest.raises(ValueError, match="max_sellable_amount requires base_quantity"):
        await client.create_market_order(
            side="Sell",
            quote_quantity=10_000,
            asset_id=AssetIdentifier("200"),
            max_sellable_amount=1_000,
        )


@pytest.mark.anyio
async def test_prepare_limit_order_request_threads_trigger():
    client = _CapturingClient(user=User())

    _, signed = await client.prepare_limit_order_request(
        AssetIdentifier("200"),
        100_00,
        10,
        "Buy",
        None,
        None,
        None,
        _trigger_above(price=123_45),
    )

    assert signed.model_dump()["order"]["trigger"] == {
        "parent_order_id": None,
        "condition": {"PriceAbove": {"price": 123_45}},
    }
