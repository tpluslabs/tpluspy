from typing import Any

import pytest

from tplus.client.orderbook import OrderBookClient
from tplus.model.asset_identifier import AssetIdentifier


class _DummyUser:
    public_key = "ab" * 32


def _trade(trade_id: int, timestamp_ns: int, asset_id: str = "1") -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "trade_id": trade_id,
        "order_id": "oid",
        "price": "100",
        "quantity": "1",
        "timestamp_ns": timestamp_ns,
        "is_maker": False,
        "is_buyer": True,
        "status": "Confirmed",
        "rollback_reason": None,
    }


def _position(sub_account_index: int, name: str, side: str = "long") -> dict[str, Any]:
    return {
        "asset_id": "1",
        "sub_account_index": sub_account_index,
        "name": name,
        "side": side,
        "size": "1.5",
        "entry_price": "100",
        "mark_price": "101",
        "unrealized_pnl": "1.5",
        "margin": "10",
        "leverage": "4",
        "liquidation_price": "90",
        "base_credits": "1.5",
        "base_liabilities": "0",
        "quote_credits": "0",
        "quote_liabilities": "150",
    }


def _client_returning(payload: Any) -> tuple[OrderBookClient, list[dict[str, Any] | None]]:
    """A client whose `_request` echoes `payload` and records the params it was called with."""
    captured: list[dict[str, Any] | None] = []

    class DummyClient(OrderBookClient):
        async def _request(self, method, endpoint, json_data=None, params=None, **kwargs):
            captured.append(params)
            return payload

    return DummyClient("http://example.com", default_user=_DummyUser()), captured  # type: ignore


@pytest.mark.anyio
async def test_get_user_trades_page_parses_envelope():
    envelope = {
        "trades": [_trade(2, 300), _trade(1, 100)],
        "page": 0,
        "limit": 2,
        "total_trades": 5,
        "total_pages": 3,
        "cursor_size": 2,
        "has_next_page": True,
        "next_page": 1,
    }
    client, captured = _client_returning(envelope)
    page = await client.get_user_trades_page(page=0, limit=2)
    assert [t.timestamp_ns for t in page.trades] == [300, 100]
    assert page.total_trades == 5
    assert page.has_next_page is True
    assert page.next_page == 1
    assert captured == [{"page": 0, "limit": 2}]


@pytest.mark.anyio
async def test_get_user_trades_returns_list_from_envelope():
    envelope = {
        "trades": [_trade(2, 300), _trade(1, 100)],
        "page": 0,
        "limit": 100,
        "total_trades": 2,
        "total_pages": 1,
        "cursor_size": 2,
        "has_next_page": False,
        "next_page": None,
    }
    client, _ = _client_returning(envelope)
    trades = await client.get_user_trades()
    assert [t.trade_id for t in trades] == [2, 1]


@pytest.mark.anyio
async def test_get_user_trades_page_tolerates_bare_list():
    client, _ = _client_returning([_trade(1, 100)])
    page = await client.get_user_trades_page()
    assert page.total_trades == 1
    assert page.has_next_page is False


@pytest.mark.anyio
async def test_get_user_trades_for_asset_passes_asset_in_path():
    captured_endpoints: list[str] = []

    class DummyClient(OrderBookClient):
        async def _request(self, method, endpoint, json_data=None, params=None, **kwargs):
            captured_endpoints.append(endpoint)
            return []

    client = DummyClient("http://example.com", default_user=_DummyUser())  # type: ignore
    await client.get_user_trades_for_asset(AssetIdentifier("200"))
    assert captured_endpoints[0].endswith("/200")


@pytest.mark.anyio
async def test_get_user_positions_page_parses_envelope():
    envelope = {
        "positions": [_position(1, "Margin"), _position(2, "Iso")],
        "page": 0,
        "limit": 1,
        "total_positions": 2,
        "total_pages": 2,
        "cursor_size": 1,
        "has_next_page": True,
        "next_page": 1,
    }
    client, captured = _client_returning(envelope)
    page = await client.get_user_positions_page(sub_account=1, page=0, limit=1)
    assert page.total_positions == 2
    assert page.has_next_page is True
    assert captured == [{"sub_account": 1, "page": 0, "limit": 1}]


@pytest.mark.anyio
async def test_get_user_positions_returns_list():
    envelope = {
        "positions": [_position(1, "Margin")],
        "page": 0,
        "limit": 100,
        "total_positions": 1,
        "total_pages": 1,
        "cursor_size": 1,
        "has_next_page": False,
        "next_page": None,
    }
    client, _ = _client_returning(envelope)
    positions = await client.get_user_positions()
    assert len(positions) == 1
    assert positions[0].name == "Margin"


@pytest.mark.anyio
async def test_get_user_orders_parses_envelope():
    envelope = {
        "orders": [],
        "page": 0,
        "limit": 100,
        "total_orders": 0,
        "total_pages": 0,
        "cursor_size": 0,
        "has_next_page": False,
        "next_page": None,
    }
    client, captured = _client_returning(envelope)
    orders, raw = await client.get_user_orders(page=2, limit=50)
    assert orders == []
    assert raw["has_next_page"] is False
    assert captured == [{"page": 2, "limit": 50}]
