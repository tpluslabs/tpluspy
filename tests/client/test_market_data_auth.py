from typing import Any

import pytest

from tplus.client import MarketDataClient
from tplus.client.auth import AuthenticatedClient
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
    await client.get_user_trades_page(user=user)

    assert captured["endpoint"] == f"/trades/user/{user.public_key}"
    assert captured["requires_auth"] is True
    assert captured["user"] is user


@pytest.mark.anyio
async def test_get_user_trades_page_sends_history_filters(mocker):
    client = MarketDataClient(base_url="http://127.0.0.1:8011")
    get = mocker.patch.object(client, "_get", new=mocker.AsyncMock(return_value=[]))

    await client.get_user_trades_page(
        user=User(), start_time=100, end_time=200, side="sell", limit=5
    )

    assert get.call_args.kwargs["params"] == {
        "start_time": 100,
        "end_time": 200,
        "side": "sell",
        "limit": 5,
    }


@pytest.mark.anyio
async def test_get_user_orders_sends_history_filters(mocker):
    client = MarketDataClient(base_url="http://127.0.0.1:8011")
    get = mocker.patch.object(client, "_get", new=mocker.AsyncMock(return_value={"orders": []}))

    await client.get_user_orders(user=User(), start_time=100, side="buy", status="cancelled")

    assert get.call_args.kwargs["params"] == {
        "start_time": 100,
        "side": "buy",
        "status": "cancelled",
    }


@pytest.mark.anyio
async def test_get_user_orders_omits_unset_filters(mocker):
    client = MarketDataClient(base_url="http://127.0.0.1:8011")
    get = mocker.patch.object(client, "_get", new=mocker.AsyncMock(return_value={"orders": []}))

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
