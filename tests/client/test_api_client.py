import time
from types import SimpleNamespace

import httpx
import pytest

from tplus.client.api import TplusApiClient
from tplus.utils.user import User


class FakeGateway:
    """Simulates the API gateway fronting both OMS and MDS on one origin."""

    def __init__(self) -> None:
        self.nonce_calls = 0
        self.auth_calls = 0
        self.auth_headers: dict[str, str | None] = {}

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/nonce/"):
            self.nonce_calls += 1
            return httpx.Response(200, json={"value": "n"})

        if path == "/auth":
            self.auth_calls += 1
            return httpx.Response(
                200,
                json={"token": "tok-1", "expiry_ns": time.time_ns() + 3_600_000_000_000},
            )

        if path.startswith("/inventory/user/"):
            self.auth_headers["inventory"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"balances": []})

        if path == "/tickers":
            return httpx.Response(200, json=[{"symbol": "BTC"}])

        if path.startswith("/trades/user/"):
            self.auth_headers["trades"] = request.headers.get("Authorization")
            return httpx.Response(
                200,
                json={
                    "trades": [],
                    "total_trades": 0,
                    "page": 0,
                    "limit": 0,
                    "total_pages": 0,
                    "cursor_size": 0,
                    "has_next_page": False,
                },
            )

        return httpx.Response(404)


def make_client(gateway: FakeGateway) -> TplusApiClient:
    transport = httpx.MockTransport(gateway.handle)
    httpx_client = httpx.AsyncClient(base_url="http://test", transport=transport)
    return TplusApiClient(
        base_url="http://test",
        default_user=User(),
        client=httpx_client,
    )


@pytest.mark.anyio
async def test_tplus_api_client_shares_one_token_across_both_services():
    gateway = FakeGateway()
    client = make_client(gateway)

    inventory = await client.oms.get_user_inventory()
    trades = await client.mds.get_user_trades()

    assert inventory == {"balances": []}
    assert trades == []

    assert gateway.auth_calls == 1
    assert gateway.nonce_calls == 1
    assert gateway.auth_headers["inventory"] == "Bearer tok-1"
    assert gateway.auth_headers["trades"] == "Bearer tok-1"

    await client.close()


def test_tplus_api_client_subclients_share_connection_and_auth():
    gateway = FakeGateway()
    client = make_client(gateway)

    assert client.oms._client is client._client
    assert client.mds._client is client._client
    assert client.oms._auth is client._auth
    assert client.mds._auth is client._auth


@pytest.mark.anyio
async def test_getattr_proxies_to_mds():
    gateway = FakeGateway()
    client = make_client(gateway)

    tickers = await client.get_tickers()

    assert tickers == [{"symbol": "BTC"}]

    await client.close()


@pytest.mark.anyio
async def test_getattr_proxies_to_oms():
    gateway = FakeGateway()
    client = make_client(gateway)

    inventory = await client.get_user_inventory()

    assert inventory == {"balances": []}

    await client.close()


def test_getattr_prefers_oms_on_collision():
    gateway = FakeGateway()
    client = make_client(gateway)
    client.oms = SimpleNamespace(shared="from-oms")  # type: ignore[assignment]
    client.mds = SimpleNamespace(shared="from-mds")  # type: ignore[assignment]

    assert client.shared == "from-oms"


def test_getattr_falls_through_to_mds():
    gateway = FakeGateway()
    client = make_client(gateway)
    client.oms = SimpleNamespace(only_oms="oms")  # type: ignore[assignment]
    client.mds = SimpleNamespace(only_mds="mds")  # type: ignore[assignment]

    assert client.only_mds == "mds"


def test_getattr_raises_for_private_names():
    gateway = FakeGateway()
    client = make_client(gateway)
    client.oms = SimpleNamespace(_secret="nope")  # type: ignore[assignment]
    client.mds = SimpleNamespace()  # type: ignore[assignment]

    with pytest.raises(AttributeError):
        _ = client._secret


def test_getattr_does_not_shadow_inherited_attributes():
    gateway = FakeGateway()
    client = make_client(gateway)

    assert client._auth is client.oms._auth
    assert client._client is client._client
    assert getattr(client.close, "__self__", None) is client


def test_getattr_raises_naming_facade_on_miss():
    gateway = FakeGateway()
    client = make_client(gateway)

    with pytest.raises(AttributeError, match="TplusApiClient"):
        _ = client.does_not_exist_anywhere
