import json
from typing import Any

import httpx
import pytest

from tplus.client.orderbook import OrderBookClient
from tplus.model.types import U64_MAX
from tplus.types import UserType
from tplus.utils.user import DelegatedUser, User


@pytest.mark.anyio
async def test_get_multisig_config_fetches_authenticated_user():
    user = User()
    expected = {
        "master_weight": 2,
        "signers": [],
        "thresholds": {"low": 1, "medium": 1, "high": 2},
    }
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if request.url.path.startswith("/nonce/"):
            return httpx.Response(200, json={"value": "n"})
        if request.url.path == "/auth":
            return httpx.Response(
                200,
                json={"token": "tok", "expiry_ns": 9_999_999_999_999_999_999},
            )
        if request.url.path == f"/multisig/config/{user.public_key}":
            assert request.headers["Authorization"] == "Bearer tok"
            assert request.headers["User-Id"] == user.public_key
            return httpx.Response(200, json=expected)
        return httpx.Response(404)

    httpx_client = httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.MockTransport(handler),
    )
    client = OrderBookClient(
        "http://test",
        default_user=user,
        client=httpx_client,
    )

    assert await client.get_multisig_config() == expected
    assert seen_paths == [
        f"/nonce/{user.public_key}",
        "/auth",
        f"/multisig/config/{user.public_key}",
    ]

    await client.close()


@pytest.mark.anyio
async def test_get_multisig_config_returns_default_when_not_stored():
    user = User()

    class DummyClient(OrderBookClient):
        async def _request(
            self,
            method: str,
            endpoint: str,
            json_data: dict[str, Any] | None = None,
            params: dict[str, Any] | None = None,
            *,
            requires_auth: bool = True,
            user: UserType | None = None,
            headers: dict[str, str] | None = None,
            request_timeout: float | None = None,
        ) -> dict[str, Any]:
            _ = method, endpoint, json_data, params, requires_auth, user, headers, request_timeout
            from tplus.exceptions import NotFoundError

            raise NotFoundError(
                code="MULTISIG_CONFIG_NOT_FOUND",
                message="Multisig config not found",
                status_code=404,
            )

    client = DummyClient("http://example.com", default_user=user)

    assert await client.get_multisig_config() == {
        "master_weight": 1,
        "signers": [],
        "thresholds": {"low": 1, "medium": 1, "high": 1},
    }

    await client.close()


@pytest.mark.anyio
async def test_add_multisig_signer_authenticates_before_fetching_request_nonce():
    user = User()
    signer = User()
    seen_paths: list[str] = []
    add_payload: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal add_payload
        seen_paths.append(request.url.path)
        if request.url.path == f"/nonce/{user.public_key}":
            if seen_paths.count(request.url.path) == 1:
                return httpx.Response(200, json={"value": "auth-nonce"})
            assert request.headers["Authorization"] == "Bearer tok"
            return httpx.Response(200, json={"value": "request-nonce", "ce_nonce": 7})
        if request.url.path == "/auth":
            return httpx.Response(
                200,
                json={"token": "tok", "expiry_ns": 9_999_999_999_999_999_999},
            )
        if request.url.path == "/multisig/add-signer":
            assert request.headers["Authorization"] == "Bearer tok"
            add_payload = json.loads(request.content)
            return httpx.Response(200, json={"added": True})
        return httpx.Response(404)

    httpx_client = httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.MockTransport(handler),
    )
    client = OrderBookClient("http://test", default_user=user, client=httpx_client)

    assert await client.add_multisig_signer(signer) == {"added": True}
    assert seen_paths == [
        f"/nonce/{user.public_key}",
        "/auth",
        f"/nonce/{user.public_key}",
        "/multisig/add-signer",
    ]
    assert add_payload["inner"] == {
        "user": user.public_key,
        "oms_nonce": "request-nonce",
        "ce_nonce": 7,
        "signer": {"Ed25519": signer.public_key_vec},
        "weight": 1,
        "session_duration_ns": U64_MAX,
    }
    assert add_payload["additional_signers"] == []
    user.vk.verify(
        bytes(add_payload["signature"]),
        json.dumps(add_payload["inner"], separators=(",", ":")).encode(),
    )

    await client.close()


@pytest.mark.anyio
async def test_add_multisig_signer_supports_delegated_authorizer():
    account = User()
    credential = User()
    delegated = DelegatedUser(account.public_key, credential)
    signer = User()
    nonce_calls = 0
    auth_payload: dict[str, Any] = {}
    add_payload: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal nonce_calls, auth_payload, add_payload
        if request.url.path == f"/nonce/{account.public_key}":
            nonce_calls += 1
            if nonce_calls == 1:
                return httpx.Response(200, json={"value": "auth-nonce"})
            return httpx.Response(200, json={"value": "request-nonce", "ce_nonce": 8})
        if request.url.path == "/auth":
            auth_payload = json.loads(request.content)
            return httpx.Response(
                200,
                json={"token": "tok", "expiry_ns": 9_999_999_999_999_999_999},
            )
        if request.url.path == "/multisig/add-signer":
            add_payload = json.loads(request.content)
            return httpx.Response(200, json={"added": True})
        return httpx.Response(404)

    httpx_client = httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.MockTransport(handler),
    )
    client = OrderBookClient("http://test", default_user=delegated, client=httpx_client)

    assert await client.add_multisig_signer(signer) == {"added": True}
    assert auth_payload["user_id"] == account.public_key
    assert auth_payload["signature"] == []
    assert add_payload["inner"]["user"] == account.public_key
    assert add_payload["inner"]["signer"] == {"Ed25519": signer.public_key_vec}
    assert add_payload["signature"] == []
    assert add_payload["additional_signers"][0]["signer"] == {"Ed25519": credential.public_key_vec}
    credential.vk.verify(
        bytes(add_payload["additional_signers"][0]["signature"]),
        json.dumps(add_payload["inner"], separators=(",", ":")).encode(),
    )

    await client.close()


@pytest.mark.anyio
async def test_add_multisig_signer_rejects_delegated_signer():
    user = User()
    delegated_signer = DelegatedUser(User().public_key, User())
    client = OrderBookClient(default_user=user)

    with pytest.raises(ValueError, match="signer must be a master-key User"):
        await client.add_multisig_signer(delegated_signer)

    await client.close()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"weight": 0}, "weight must be greater than zero"),
        ({"weight": -1}, "weight must be greater than zero"),
        ({"session_duration_ns": -1}, "session_duration_ns must be between"),
        ({"session_duration_ns": 0}, "session_duration_ns must be between"),
        ({"session_duration_ns": U64_MAX + 1}, "session_duration_ns must be between"),
    ],
)
async def test_add_multisig_signer_validates_config(kwargs, message):
    client = OrderBookClient(default_user=User())

    with pytest.raises(ValueError, match=message):
        await client.add_multisig_signer(User(), **kwargs)

    await client.close()
