from typing import Any

import pytest

from tplus.client import MarketDataClient
from tplus.client.auth import AuthenticatedClient
from tplus.utils.user import User


@pytest.mark.anyio
async def test_authed_get_requires_auth_client():
    client = MarketDataClient(base_url="http://127.0.0.1:8011")
    with pytest.raises(ValueError, match="auth_client"):
        await client._authed_get("/trades/user/abc")


@pytest.mark.anyio
async def test_authed_get_borrows_oms_bearer_headers(monkeypatch: pytest.MonkeyPatch):
    auth_client = AuthenticatedClient(base_url="http://127.0.0.1:8000")

    async def fake_ensure(user: Any = None) -> None:
        return None

    monkeypatch.setattr(auth_client, "_ensure_auth", fake_ensure)
    monkeypatch.setattr(
        auth_client,
        "_get_auth_headers",
        lambda user=None: {"Authorization": "Bearer tok-1", "User-Id": "abc"},
    )

    client = MarketDataClient(base_url="http://127.0.0.1:8011", auth_client=auth_client)

    captured: dict[str, Any] = {}

    async def fake_send(method: str, relative_url: str, *, params=None, headers=None, **_: Any):
        captured["method"] = method
        captured["url"] = relative_url
        captured["headers"] = headers
        return object()

    monkeypatch.setattr(client, "_send", fake_send)
    monkeypatch.setattr(client, "_handle_response", lambda _resp: [])

    result = await client._authed_get("/trades/user/abc", user=User(), params={"page": 0})

    assert result == []
    assert captured["method"] == "GET"
    assert captured["url"] == "/trades/user/abc"
    assert captured["headers"]["Authorization"] == "Bearer tok-1"
    assert captured["headers"]["User-Id"] == "abc"
