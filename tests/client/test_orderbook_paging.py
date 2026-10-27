from typing import Any

import pytest

from tplus.client.market_data import MarketDataClient
from tplus.client.orderbook import OrderBookClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.market import MarketTypeFilter
from tplus.model.trades import UserTradesPage
from tplus.utils.user import User


class _DummyUser:
    public_key = "ab" * 32


def _trade(trade_id: int, timestamp_ns: int, asset_id: str = "1") -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "order_id": f"oid-{trade_id}",
        "price": "100",
        "quantity": "1",
        "timestamp_ns": timestamp_ns,
        "is_maker": False,
        "is_buyer": True,
        "status": "Confirmed",
        "rollback_reason": None,
        "is_liquidation": False,
        "is_auto_deleverage": False,
        "sub_account": 1,
        "trading_fee": "0.1",
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


def _client_returning(
    payload: Any, base: type = OrderBookClient
) -> tuple[Any, list[dict[str, Any] | None]]:
    """A client whose `_request` echoes `payload` and records the params it was called with."""
    captured: list[dict[str, Any] | None] = []

    class DummyClient(base):  # type: ignore[misc, valid-type]
        async def _request(self, method, endpoint, json_data=None, params=None, **kwargs):
            captured.append(params)
            return payload

    return DummyClient("http://example.com", default_user=_DummyUser()), captured  # type: ignore


@pytest.mark.anyio
async def test_get_user_trades_parses_envelope():
    envelope = {
        "trades": [_trade(2, 300), _trade(1, 100)],
        "has_next_page": True,
        "next_page": 1,
    }
    client, captured = _client_returning(envelope, MarketDataClient)
    page = await client.get_user_trades(page=0, limit=2)
    assert [t.timestamp_ns for t in page.trades] == [300, 100]
    assert page.has_next_page is True
    assert page.next_page == 1
    assert captured == [{"page": 0, "limit": 2}]


@pytest.mark.anyio
async def test_get_user_trades_is_list_like():
    envelope = {
        "trades": [_trade(2, 300), _trade(1, 100)],
        "has_next_page": False,
        "next_page": None,
    }
    client, _ = _client_returning(envelope, MarketDataClient)
    trades = await client.get_user_trades()
    assert [t.order_id for t in trades] == ["oid-2", "oid-1"]
    assert len(trades) == 2


@pytest.mark.anyio
async def test_get_user_trades_tolerates_bare_list():
    client, _ = _client_returning([_trade(1, 100)], MarketDataClient)
    page = await client.get_user_trades()
    assert page.has_next_page is False


@pytest.mark.anyio
async def test_get_user_trades_for_asset_passes_asset_in_path():
    captured_endpoints: list[str] = []

    class DummyClient(MarketDataClient):
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


@pytest.mark.anyio
async def test_get_markets_parses_page_and_symbol_map():
    envelope = {
        "markets": [
            {
                "asset_id": "1",
                "book_price_decimals": 2,
                "book_quantity_decimals": 4,
                "max_leverage": "3.77",
                "isolated_only": False,
                "fee_schedule": {
                    "fee_account": "ab" * 32,
                    "global": [
                        {
                            "min_rolling_volume_usd": 0,
                            "taker_fee_rate": 500,
                            "maker_fee_rate": 100,
                            "maker_rebate_rate_of_taker_fee": None,
                        }
                    ],
                    "per_asset": [],
                },
            }
        ],
        "total_markets": 1,
        "page": 2,
        "limit": 50,
        "total_pages": 3,
        "cursor_size": 1,
        "has_next_page": False,
        "next_page": None,
        "symbol_map": {
            "1": {
                "index": 1,
                "symbol": "ETH",
                "name": "Ethereum",
                "asset_class": "ETH",
                "representations": ["WETH"],
            }
        },
    }
    client, captured = _client_returning(envelope)
    page = await client.get_markets(include_symbol_map=True, page=2, limit=50)
    assert page[0].max_leverage == "3.77"
    assert len(page[0].fee_schedule.global_) == 1
    assert page.symbol_map[1].symbol == "ETH"
    assert page.symbol_map[1].name == "Ethereum"
    assert page.symbol_map[1].representations == ["WETH"]
    assert captured == [{"include_symbol_map": "true", "page": 2, "limit": 50}]


@pytest.mark.anyio
async def test_get_markets_defaults_to_one_full_page():
    envelope = {
        "markets": [],
        "total_markets": 0,
        "page": 0,
        "limit": 1000,
        "total_pages": 0,
        "cursor_size": 0,
        "has_next_page": False,
        "next_page": None,
    }
    client, captured = _client_returning(envelope)
    page = await client.get_markets()
    assert page.symbol_map is None
    assert captured == [{"page": 0, "limit": 1000}]


@pytest.mark.anyio
@pytest.mark.parametrize("market_type", [MarketTypeFilter.SPOT, "spot", "SPOT"])
async def test_get_markets_sends_market_type(market_type):
    envelope = {
        "markets": [],
        "total_markets": 0,
        "page": 0,
        "limit": 1000,
        "total_pages": 0,
        "cursor_size": 0,
        "has_next_page": False,
        "next_page": None,
    }
    client, captured = _client_returning(envelope)
    await client.get_markets(market_type=market_type)
    assert captured == [{"page": 0, "limit": 1000, "market_type": "spot"}]


@pytest.mark.anyio
async def test_get_markets_rejects_unknown_market_type():
    client, captured = _client_returning({})
    with pytest.raises(ValueError):
        await client.get_markets(market_type="perp")
    assert captured == []


@pytest.mark.anyio
@pytest.mark.parametrize("limit", [1, 999, 1000])
async def test_user_trades_requests_one_page_with_limit(limit, mocker):
    user = User()
    client = MarketDataClient(default_user=user)
    get = mocker.patch.object(
        client,
        "_get",
        new_callable=mocker.AsyncMock,
        return_value={
            "trades": [_trade(1, 100)],
            "has_next_page": True,
            "next_page": 3,
        },
    )

    result = await client.get_user_trades(limit=limit, page=2)

    get.assert_awaited_once_with(
        f"/trades/user/{user.public_key}",
        params={"limit": limit, "page": 2},
        requires_auth=True,
        user=None,
    )
    assert isinstance(result, UserTradesPage)
    assert result.next_page == 3
    assert len(result) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("asset", [None, AssetIdentifier("1")])
async def test_user_trades_caps_limit_and_warns_without_following_next_page(asset, mocker):
    user = User()
    client = MarketDataClient(default_user=user)
    get = mocker.patch.object(
        client,
        "_get",
        new_callable=mocker.AsyncMock,
        return_value={
            "trades": [_trade(i, i) for i in range(1000, 0, -1)],
            "has_next_page": True,
            "next_page": 1,
        },
    )

    with pytest.warns(UserWarning, match="Paginate"):
        if asset is None:
            result = await client.get_user_trades(limit=2500)
        else:
            result = await client.get_user_trades_for_asset(asset, limit=2500)

    endpoint = f"/trades/user/{user.public_key}"
    if asset is not None:
        endpoint += f"/{asset}"
    get.assert_awaited_once_with(
        endpoint,
        params={"limit": 1000},
        requires_auth=True,
        user=None,
    )
    assert len(result) == 1000
    assert result[0].timestamp_ns == 1000
    assert result[-1].timestamp_ns == 1
    assert result.next_page == 1


@pytest.mark.anyio
async def test_user_trades_default_preserves_server_limit_and_page_type(mocker):
    user = User()
    client = MarketDataClient()
    get = mocker.patch.object(
        client,
        "_get",
        new_callable=mocker.AsyncMock,
        return_value={
            "trades": [_trade(1, 1)],
            "has_next_page": True,
            "next_page": 1,
        },
    )

    recent = await client.get_user_trades(user=user)

    get.assert_awaited_once_with(
        f"/trades/user/{user.public_key}",
        params=None,
        requires_auth=True,
        user=user,
    )
    assert isinstance(recent, UserTradesPage)
    assert len(recent) == 1
    assert recent.next_page == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "limit,error",
    [
        (0, ValueError),
        (-1, ValueError),
        (1.5, TypeError),
        ("100", TypeError),
        (True, TypeError),
        (False, TypeError),
    ],
)
@pytest.mark.parametrize("asset", [None, AssetIdentifier("1")])
async def test_user_trades_rejects_invalid_limit_before_request(limit, error, asset, mocker):
    client = MarketDataClient()
    get = mocker.patch.object(client, "_get", new_callable=mocker.AsyncMock)

    with pytest.raises(error, match="positive integer"):
        if asset is None:
            await client.get_user_trades(limit=limit)
        else:
            await client.get_user_trades_for_asset(asset, limit=limit)

    get.assert_not_awaited()
