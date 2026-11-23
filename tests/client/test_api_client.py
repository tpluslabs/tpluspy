import time
from types import SimpleNamespace

import httpx
import pytest
from websockets.datastructures import Headers
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response

from tplus.client.api import TplusApiClient
from tplus.client.base import BaseClient
from tplus.model.auth import AuthRequestBody
from tplus.utils.user import User


class FakeGateway:
    """Simulates the API gateway fronting both OMS and MDS on one origin."""

    def __init__(self) -> None:
        self.oms_nonce_calls = 0
        self.oms_auth_calls = 0
        self.mds_nonce_calls = 0
        self.mds_auth_calls = 0
        self.auth_headers: dict[str, dict[str, str | None]] = {}

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/market-data/nonce/"):
            self.mds_nonce_calls += 1
            return httpx.Response(200, json={"value": "mds-n"})

        if path == "/market-data/auth":
            self.mds_auth_calls += 1
            return httpx.Response(
                200,
                json={"token": "mds-tok", "expiry_ns": time.time_ns() + 3_600_000_000_000},
            )

        if path.startswith("/nonce/"):
            self.oms_nonce_calls += 1
            return httpx.Response(200, json={"value": "oms-n"})

        if path == "/auth":
            self.oms_auth_calls += 1
            return httpx.Response(
                200,
                json={"token": "oms-tok", "expiry_ns": time.time_ns() + 3_600_000_000_000},
            )

        if path.startswith("/inventory/user/"):
            self._record("inventory", request)
            return httpx.Response(200, json={"balances": []})

        if path == "/tickers":
            return httpx.Response(
                200,
                json=[{"asset_id": "1", "volume_24h": "0", "timestamp_ns": 1}],
            )

        if path.startswith("/trades/user/"):
            self._record("trades", request)
            return httpx.Response(
                200,
                json={
                    "trades": [],
                    "has_next_page": False,
                    "next_page": None,
                },
            )

        return httpx.Response(404)

    def _record(self, endpoint: str, request: httpx.Request) -> None:
        self.auth_headers[endpoint] = {
            name: request.headers.get(name)
            for name in ("Authorization", "Oms-Authorization", "Mds-Authorization")
        }


def make_client(gateway: FakeGateway) -> TplusApiClient:
    transport = httpx.MockTransport(gateway.handle)
    httpx_client = httpx.AsyncClient(base_url="http://test", transport=transport)
    return TplusApiClient(
        base_url="http://test",
        default_user=User(),
        client=httpx_client,
    )


@pytest.mark.anyio
async def test_tplus_api_client_uses_service_scoped_tokens():
    gateway = FakeGateway()
    client = make_client(gateway)

    inventory = await client.oms.get_user_inventory()
    trades = await client.mds.get_user_trades()

    assert inventory == {"balances": []}
    assert trades == []

    assert gateway.oms_auth_calls == 1
    assert gateway.oms_nonce_calls == 1
    assert gateway.mds_auth_calls == 1
    assert gateway.mds_nonce_calls == 1
    assert gateway.auth_headers["inventory"]["Authorization"] == "Bearer oms-tok"
    assert gateway.auth_headers["trades"]["Authorization"] == "Bearer mds-tok"

    # Both tokens ride on every request.
    for endpoint in ("inventory", "trades"):
        assert gateway.auth_headers[endpoint]["Oms-Authorization"] == "Bearer oms-tok"
        assert gateway.auth_headers[endpoint]["Mds-Authorization"] == "Bearer mds-tok"

    await client.close()


def test_tplus_api_client_subclients_share_connection_but_not_mds_auth():
    gateway = FakeGateway()
    client = make_client(gateway)

    assert client.oms._client is client._client
    assert client.mds._client is client._client
    assert client.oms._auth is client._auth
    assert client.mds._auth is not client._auth
    assert client.mds._auth_path_prefix == "/market-data"


@pytest.mark.anyio
async def test_getattr_proxies_to_mds():
    gateway = FakeGateway()
    client = make_client(gateway)

    tickers = await client.get_tickers()

    assert [str(ticker.asset_id) for ticker in tickers] == ["1"]

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


@pytest.fixture(params=[1, 2], ids=["shard_1", "shard_2"])
def shard_gateway(request):
    """HTTP transport fixture for a user whose two token authorities share an owner."""
    state = SimpleNamespace(
        shard=request.param,
        user=User(),
        generations={"oms": 0, "mds": 0},
        minimum_generation={"oms": 1, "mds": 1},
        data_requests=[],
        rejection_code="GATEWAY_ROUTE_CHANGED",
        failure=None,
    )

    def token(service: str, generation: int) -> str:
        return f"{service}-shard-{state.shard}-token-{generation}"

    def handle(req: httpx.Request) -> httpx.Response:
        assert req.url.host == "gateway.test"
        path = req.url.path
        service = "mds" if path.startswith(("/market-data/", "/trades/")) else "oms"
        prefix = "/market-data" if service == "mds" else ""
        nonce = f"{service}-shard-{state.shard}-nonce"
        if path == f"{prefix}/nonce/{state.user.public_key}":
            return httpx.Response(200, json={"value": nonce})
        if path == f"{prefix}/auth":
            body = AuthRequestBody.model_validate_json(req.content)
            assert body.user_id == state.user.public_key
            assert body.nonce == nonce
            state.user.vk.verify(bytes(body.signature), nonce.encode())
            state.generations[service] += 1
            return httpx.Response(
                200,
                json={
                    "token": token(service, state.generations[service]),
                    "expiry_ns": time.time_ns() + 3_600_000_000_000,
                },
            )

        state.data_requests.append(req)
        assert req.headers["User-Id"] == state.user.public_key
        if state.failure is not None:
            status, code = state.failure
            error = {"code": code, "message": "refused", "retryable": False} if code else "refused"
            return httpx.Response(status, json={"error": error})
        if req.headers.get("Authorization") != (
            f"Bearer {token(service, state.minimum_generation[service])}"
        ):
            # What the services answer for a stale token, and the gateway for a moved user.
            error = {"code": state.rejection_code, "message": "refused", "retryable": False}
            if state.rejection_code == "GATEWAY_ROUTE_CHANGED":
                error["details"] = {"request_executed": False}
            return httpx.Response(401, json={"error": error})
        if path == f"/inventory/user/{state.user.public_key}":
            return httpx.Response(200, json={"balances": [], "owner_shard": state.shard})
        if path == f"/trades/user/{state.user.public_key}":
            return httpx.Response(
                200,
                json={
                    "trades": [
                        {
                            "asset_id": "1",
                            "order_id": f"shard-{state.shard}-order",
                            "price": "100",
                            "quantity": "2",
                            "timestamp_ns": 1,
                            "is_maker": True,
                            "is_buyer": False,
                            "status": "Finalized",
                            "is_liquidation": False,
                            "is_auto_deleverage": False,
                            "sub_account": 0,
                            "trading_fee": "0",
                        }
                    ],
                    "has_next_page": False,
                    "next_page": None,
                },
            )
        return httpx.Response(404)

    http = httpx.AsyncClient(base_url="http://gateway.test", transport=httpx.MockTransport(handle))
    client = TplusApiClient("http://gateway.test", default_user=state.user, client=http)
    return client, state


@pytest.mark.anyio
async def test_gateway_uses_paired_sessions_for_users_on_either_shard(shard_gateway):
    client, state = shard_gateway
    async with client:
        inventory = await client.oms.get_user_inventory()
        trades = await client.mds.get_user_trades()

    assert inventory["owner_shard"] == state.shard
    assert [trade.order_id for trade in trades] == [f"shard-{state.shard}-order"]
    assert state.generations == {"oms": 1, "mds": 1}
    for req in state.data_requests:
        assert req.headers["Oms-Authorization"] == f"Bearer oms-shard-{state.shard}-token-1"
        assert req.headers["Mds-Authorization"] == f"Bearer mds-shard-{state.shard}-token-1"


@pytest.mark.anyio
@pytest.mark.parametrize("service", ["oms", "mds"])
@pytest.mark.parametrize("code", ["UNAUTHORIZED", "GATEWAY_ROUTE_CHANGED"])
async def test_gateway_refreshes_only_rejected_service_after_stale_routing(
    shard_gateway, service, code
):
    client, state = shard_gateway
    async with client:
        await client.oms.get_user_inventory()
        state.data_requests.clear()
        state.minimum_generation[service] = 2
        state.rejection_code = code

        if service == "oms":
            await client.oms.get_user_inventory()
        else:
            await client.mds.get_user_trades()

        other = "mds" if service == "oms" else "oms"
        assert state.generations == {service: 2, other: 1}
        assert len(state.data_requests) == 2
        assert [req.headers["Authorization"] for req in state.data_requests] == [
            f"Bearer {service}-shard-{state.shard}-token-1",
            f"Bearer {service}-shard-{state.shard}-token-2",
        ]
        assert state.data_requests[-1].headers[f"{service}-Authorization"] == (
            f"Bearer {service}-shard-{state.shard}-token-2"
        )
        assert state.data_requests[-1].headers[f"{other}-Authorization"] == (
            f"Bearer {other}-shard-{state.shard}-token-1"
        )


@pytest.mark.anyio
@pytest.mark.parametrize("service", ["oms", "mds"])
@pytest.mark.parametrize(
    ("status", "code", "attempts"),
    [
        # A refused session is refreshed once, then the second refusal is returned.
        (401, "UNAUTHORIZED", 2),
        # A new token cures none of these, so they are returned as they are.
        (401, "INVALID_SIGNATURE", 1),
        (401, None, 1),
        (403, "WRONG_AUTHORIZATION", 1),
        (421, "MANAGED_BY_ANOTHER_OMS", 1),
        (502, None, 1),
        (503, None, 1),
    ],
)
async def test_gateway_reauthentication_is_bounded_and_only_for_a_refused_session(
    shard_gateway, service, status, code, attempts
):
    client, state = shard_gateway
    async with client:
        await client.oms.get_user_inventory()
        state.data_requests.clear()
        state.failure = (status, code)
        with pytest.raises(httpx.HTTPStatusError) as rejected:
            if service == "oms":
                await client.oms.get_user_inventory()
            else:
                await client.mds.get_user_trades()

    assert rejected.value.response.status_code == status
    assert len(state.data_requests) == attempts
    assert state.generations[service] == attempts


@pytest.mark.anyio
async def test_gateway_control_option_and_facade_close_own_control_socket(mocker):
    client = TplusApiClient("http://gateway.test", default_user=User(), use_ws_control=True)
    assert client.oms._use_ws_control is True
    socket = mocker.AsyncMock()
    socket.closed = False
    client.oms._control_ws = socket

    await client.close()

    socket.close.assert_awaited_once()
    assert client.oms._control_ws is None
    assert client._client.is_closed


@pytest.mark.anyio
async def test_gateway_control_handshake_gives_up_after_one_refresh(shard_gateway, mocker):
    client, state = shard_gateway
    rejected = InvalidStatus(Response(401, "Rejected", Headers()))
    first, second = mocker.AsyncMock(), mocker.AsyncMock()
    first.__aenter__.side_effect = rejected
    second.__aenter__.side_effect = rejected
    open_ws = mocker.patch.object(
        BaseClient, "_open_ws", new=mocker.AsyncMock(side_effect=[first, second])
    )

    async with client:
        with pytest.raises(InvalidStatus):
            async with await client.oms.open_ws("/control"):
                pass

    assert open_ws.call_count == 2
    assert state.generations == {"oms": 2, "mds": 1}


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 503])
async def test_gateway_control_handshake_refresh_is_bounded_with_paired_headers(
    shard_gateway, mocker, status
):
    client, state = shard_gateway
    first = mocker.AsyncMock()
    first.__aenter__.side_effect = InvalidStatus(Response(status, "Rejected", Headers()))
    second = mocker.AsyncMock()
    second.__aenter__.return_value = "connected"
    open_ws = mocker.patch.object(
        BaseClient, "_open_ws", new=mocker.AsyncMock(side_effect=[first, second])
    )

    async with client:
        if status == 401:
            async with await client.oms.open_ws("/control") as connection:
                assert connection == "connected"
        else:
            with pytest.raises(InvalidStatus):
                async with await client.oms.open_ws("/control"):
                    pass

    attempts = 2 if status == 401 else 1
    assert open_ws.call_count == attempts
    assert state.generations == {"oms": attempts, "mds": 1}
    for generation, call in enumerate(open_ws.call_args_list, 1):
        headers = call.kwargs["extra_headers"]
        assert headers["User-Id"] == state.user.public_key
        assert headers["Authorization"] == f"Bearer oms-shard-{state.shard}-token-{generation}"
        assert headers["Oms-Authorization"] == headers["Authorization"]
        assert headers["Mds-Authorization"] == f"Bearer mds-shard-{state.shard}-token-1"
