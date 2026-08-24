from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from tplus.client import MarketDataClient
from tplus.client.auth import AuthenticatedClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.utils.user import User


def test_market_data_client_is_authenticated():
    # MDS is its own token authority; the client authenticates against MDS itself.
    assert isinstance(MarketDataClient(base_url="http://127.0.0.1:8011"), AuthenticatedClient)


@pytest.mark.anyio
async def test_user_trades_requires_mds_auth(monkeypatch: pytest.MonkeyPatch):
    client = MarketDataClient(base_url="http://127.0.0.1:8011")
    captured: dict[str, Any] = {}

    async def fake_get(endpoint: str, **kwargs: Any) -> Any:
        captured["endpoint"] = endpoint
        captured["requires_auth"] = kwargs.get("requires_auth")
        captured["user"] = kwargs.get("user")
        return []

    monkeypatch.setattr(client, "_get", fake_get)
    user = User()
    await client.get_user_trades(user=user)

    assert captured["endpoint"] == f"/trades/user/{user.public_key}"
    assert captured["requires_auth"] is True
    assert captured["user"] is user


@pytest.mark.anyio
async def test_get_user_trades_page_sends_history_filters(monkeypatch: pytest.MonkeyPatch):
    client = MarketDataClient(base_url="http://127.0.0.1:8011")
    get = AsyncMock(return_value=[])
    monkeypatch.setattr(client, "_get", get)

    await client.get_user_trades(user=User(), start_time=100, end_time=200, side="sell", limit=5)

    assert get.call_args.kwargs["params"] == {
        "start_time": 100,
        "end_time": 200,
        "side": "sell",
        "limit": 5,
    }


@pytest.mark.anyio
async def test_get_user_orders_sends_history_filters(monkeypatch: pytest.MonkeyPatch):
    client = MarketDataClient(base_url="http://127.0.0.1:8011")
    get = AsyncMock(return_value={"orders": []})
    monkeypatch.setattr(client, "_get", get)

    await client.get_user_orders(user=User(), start_time=100, side="buy", status="cancelled")

    assert get.call_args.kwargs["params"] == {
        "start_time": 100,
        "side": "buy",
        "status": "cancelled",
    }


@pytest.mark.anyio
async def test_get_user_orders_omits_unset_filters(monkeypatch: pytest.MonkeyPatch):
    client = MarketDataClient(base_url="http://127.0.0.1:8011")
    get = AsyncMock(return_value={"orders": []})
    monkeypatch.setattr(client, "_get", get)

    await client.get_user_orders(user=User())

    assert get.call_args.kwargs["params"] is None


@pytest.mark.anyio
async def test_public_endpoint_is_anonymous(monkeypatch: pytest.MonkeyPatch):
    client = MarketDataClient(base_url="http://127.0.0.1:8011")
    captured: dict[str, Any] = {}

    async def fake_get(endpoint: str, **kwargs: Any) -> Any:
        captured["requires_auth"] = kwargs.get("requires_auth")
        return []

    monkeypatch.setattr(client, "_get", fake_get)
    await client.get_tickers()

    assert captured["requires_auth"] is False


@pytest.mark.anyio
async def test_get_user_position_basis_uses_authenticated_mds_route(
    monkeypatch: pytest.MonkeyPatch,
):
    client = MarketDataClient(base_url="http://127.0.0.1:8011")
    get = AsyncMock(
        return_value=[
            {
                "sub_account": 0,
                "asset_id": "1",
                "domain": "spot",
                "side": None,
                "quantity": "1.5",
                "cost": "150",
                "entry_price": None,
                "avg_acquisition_price": "100",
                "mark_price": "110",
                "unrealized_pnl": "15",
            }
        ]
    )
    monkeypatch.setattr(client, "_get", get)
    user = User()

    rows = await client.get_user_position_basis(user=user, sub_account=0)

    get.assert_awaited_once_with(
        f"/positions/user/{user.public_key}/basis",
        params={"sub_account": 0},
        requires_auth=True,
        user=user,
    )
    assert rows[0].quantity == Decimal("1.5")
    assert rows[0].avg_acquisition_price == Decimal("100")


@pytest.mark.anyio
async def test_get_user_position_basis_for_asset_uses_asset_route_and_default_user(
    monkeypatch: pytest.MonkeyPatch,
):
    user = User()
    client = MarketDataClient(base_url="http://127.0.0.1:8011", default_user=user)
    get = AsyncMock(return_value=[])
    monkeypatch.setattr(client, "_get", get)

    rows = await client.get_user_position_basis_for_asset(AssetIdentifier("2"))

    get.assert_awaited_once_with(
        f"/positions/user/{user.public_key}/basis/2",
        params=None,
        requires_auth=True,
        user=None,
    )
    assert rows == []
