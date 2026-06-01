from typing import Any

import httpx
import pytest

from tplus.client.orderbook import OrderBookClient
from tplus.types import UserType
from tplus.utils.user import User


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
            request_timeout: float | None = None,
        ) -> dict[str, Any]:
            _ = method, endpoint, json_data, params, requires_auth, user, request_timeout
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
