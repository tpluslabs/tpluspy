import asyncio
import logging
import time
from collections.abc import Callable

import httpx
import pytest

from tplus.client.auth import Auth, AuthenticatedClient
from tplus.client.base import BaseClient, ClientSettings
from tplus.exceptions import MissingClientUserError
from tplus.model.types import UserPublicKey
from tplus.utils.user import User


class FakeAuthBackend:
    def __init__(
        self,
        *,
        token: str | Callable[[int], str] = "tok",  # noqa: S107
        expiry_ns: int | None = None,
        nonce_fail_through: int = 0,
        auth_fail_after: int | None = None,
    ) -> None:
        self._token = token
        self._expiry_ns = expiry_ns
        self.nonce_fail_through = nonce_fail_through
        self.auth_fail_after = auth_fail_after
        self.nonce_calls = 0
        self.auth_calls = 0
        self.nonce_users: list[str] = []

    @property
    def expiry_ns(self) -> int:
        return (
            self._expiry_ns if self._expiry_ns is not None else time.time_ns() + 3_600_000_000_000
        )

    def _token_for(self, attempt: int) -> str:
        return self._token(attempt) if callable(self._token) else self._token

    def handle(self, request: httpx.Request) -> httpx.Response | None:
        path = request.url.path
        if path.startswith("/nonce/"):
            self.nonce_calls += 1
            self.nonce_users.append(path.split("/nonce/", 1)[1])
            if self.nonce_calls <= self.nonce_fail_through:
                return httpx.Response(503, text="nonce down")

            return httpx.Response(200, json={"value": "n"})

        if path == "/auth":
            self.auth_calls += 1
            if self.auth_fail_after is not None and self.auth_calls > self.auth_fail_after:
                return httpx.Response(503, text="auth down")

            return httpx.Response(
                200,
                json={"token": self._token_for(self.auth_calls), "expiry_ns": self.expiry_ns},
            )

        return None


def make_handler(
    backend: FakeAuthBackend,
    on_request: Callable[[httpx.Request], httpx.Response] | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        intercepted = backend.handle(request)
        if intercepted is not None:
            return intercepted

        if on_request is not None:
            return on_request(request)

        return httpx.Response(404)

    return handler


def mock_client(
    backend: FakeAuthBackend,
    on_request: Callable[[httpx.Request], httpx.Response] | None = None,
    *,
    default_user: User | None = None,
) -> AuthenticatedClient:
    transport = httpx.MockTransport(make_handler(backend, on_request))
    httpx_client = httpx.AsyncClient(base_url="http://test", transport=transport)
    return AuthenticatedClient(
        base_url="http://test",
        default_user=default_user,
        client=httpx_client,
    )


class TestAuth:
    def test_new_auth_is_expired(self):
        auth = Auth()
        assert auth.is_expired() is True

    def test_auth_with_token_but_zero_expiry_is_expired(self):
        auth = Auth(token="some-token")
        assert auth.is_expired() is True

    def test_auth_with_valid_token_not_expired(self):
        auth = Auth(token="some-token")
        # Set expiry far in the future.
        auth.expiry_ns = time.time_ns() + (120 * 1_000_000_000)
        assert auth.is_expired() is False

    def test_auth_expired_within_safety_margin(self):
        auth = Auth(token="some-token")
        # Set expiry just 30s from now (within 60s safety margin).
        auth.expiry_ns = time.time_ns() + (30 * 1_000_000_000)
        assert auth.is_expired() is True

    def test_auth_expired_exactly_at_margin(self):
        auth = Auth(token="some-token")
        # Set expiry exactly at the margin boundary.
        auth.expiry_ns = time.time_ns() + Auth.SAFETY_MARGIN_NS
        assert auth.is_expired() is True

    def test_auth_has_lock(self):
        auth = Auth()
        assert isinstance(auth.lock, asyncio.Lock)


class TestBaseClient:
    def _make_client(self, **kwargs) -> BaseClient:
        return BaseClient(**kwargs)

    def test_constructor_with_kwargs(self):
        client = self._make_client(base_url="http://localhost:9999")
        assert isinstance(client._client, httpx.AsyncClient)
        assert client._settings.base_url == "http://localhost:9999"

    def test_constructor_with_url_string(self):
        client = BaseClient("http://localhost:9999")
        assert client._settings.base_url == "http://localhost:9999"

    def test_from_settings(self):
        settings = ClientSettings(base_url="http://localhost:9999", insecure_ssl=True)
        client = BaseClient.from_settings(settings)
        assert client._settings.base_url == "http://localhost:9999"
        assert client._settings.insecure_ssl is True

    def test_from_client_shares_internals(self):
        parent = self._make_client()
        child = BaseClient.from_client(parent)
        assert child._client is parent._client

    def test_validate_user_with_no_default_raises(self):
        client = self._make_client()
        with pytest.raises(MissingClientUserError):
            client._resolve_user()

    def test_validate_user_returns_default(self):
        class FakeUser:
            public_key = "abc"

        client = BaseClient(default_user=FakeUser())  # type: ignore
        assert client._resolve_user().public_key == "abc"  # type: ignore

    def test_validate_user_prefers_explicit(self):
        class FakeUser:
            public_key = "abc"

        class OtherUser:
            public_key = "xyz"

        client = BaseClient(default_user=FakeUser())  # type: ignore
        assert client._resolve_user(user=OtherUser()).public_key == "xyz"  # type: ignore

    def test_validate_user_public_key_from_string(self):
        key = UserPublicKey("ab" * 32)
        client = BaseClient()
        assert client._validate_user_public_key(user=key) == key

    def test_validate_user_public_key_from_user(self):
        user = User()
        client = BaseClient()
        assert client._validate_user_public_key(user=user) == user.public_key

    def test_validate_user_public_key_no_default_raises(self):
        client = self._make_client()
        with pytest.raises(MissingClientUserError):
            client._validate_user_public_key()

    def test_get_request_headers_returns_settings_headers(self):
        client = self._make_client()
        headers = client._get_request_headers()
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"

    def test_get_request_headers_returns_copy(self):
        client = self._make_client()
        h1 = client._get_request_headers()
        h1["X-Custom"] = "foo"
        h2 = client._get_request_headers()
        assert "X-Custom" not in h2

    def test_get_websocket_url_ws(self):
        client = self._make_client(base_url="http://localhost:3032")
        assert client._get_websocket_url("/stream") == "ws://localhost:3032/stream"

    def test_get_websocket_url_wss(self):
        client = self._make_client(base_url="https://example.com")
        assert client._get_websocket_url("/stream") == "wss://example.com/stream"

    def test_get_websocket_url_no_leading_slash(self):
        client = self._make_client(base_url="http://localhost:3032")
        assert client._get_websocket_url("stream") == "ws://localhost:3032/stream"

    def test_handle_response_204(self):
        req = httpx.Request("GET", "http://example.com/test")
        resp = httpx.Response(204, request=req)
        client = self._make_client()
        assert client._handle_response(resp) == {}

    def test_handle_response_empty_body(self):
        req = httpx.Request("GET", "http://example.com/test")
        resp = httpx.Response(200, request=req, content=b"")
        client = self._make_client()
        assert client._handle_response(resp) == {}

    def test_handle_response_json(self):
        req = httpx.Request("GET", "http://example.com/test")
        resp = httpx.Response(200, request=req, json={"key": "value"})
        client = self._make_client()
        assert client._handle_response(resp) == {"key": "value"}

    def test_handle_response_json_null(self):
        req = httpx.Request("GET", "http://example.com/test")
        resp = httpx.Response(
            200, request=req, text="null", headers={"content-type": "application/json"}
        )
        client = self._make_client()
        assert client._handle_response(resp) == {}

    def test_handle_response_invalid_json(self):
        req = httpx.Request("GET", "http://example.com/test")
        resp = httpx.Response(
            200, request=req, text="not json", headers={"content-type": "application/json"}
        )
        client = self._make_client()
        with pytest.raises(ValueError, match="Invalid JSON"):
            client._handle_response(resp)

    def test_handle_response_http_error(self):
        req = httpx.Request("GET", "http://example.com/test")
        resp = httpx.Response(500, request=req, text="server error")
        client = self._make_client()
        with pytest.raises(httpx.HTTPStatusError):
            client._handle_response(resp)


class TestAuthenticatedClient:
    def _make_client(self, auth=None, default_user=None) -> AuthenticatedClient:
        return AuthenticatedClient(default_user=default_user, auth=auth)

    def test_default_auth_created(self):
        client = self._make_client()
        assert isinstance(client._auth, Auth)
        assert client._auth.is_expired() is True

    def test_custom_auth_used(self):
        auth = Auth(token="pre-set")
        client = self._make_client(auth=auth)
        assert client._auth is auth
        assert client._auth.token == "pre-set"

    def test_none_auth_creates_default(self):
        client = self._make_client(auth=None)
        assert isinstance(client._auth, Auth)

    def test_get_request_headers_no_token(self):
        client = self._make_client()
        headers = client._get_request_headers()
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"

    def test_get_auth_headers_with_token(self):
        class FakeUser:
            public_key = "user123"

        auth = Auth(token="my-token")
        client = self._make_client(auth=auth, default_user=FakeUser())  # type: ignore
        headers = client._get_auth_headers()
        assert headers["Authorization"] == "Bearer my-token"
        assert headers["User-Id"] == "user123"

    def test_get_auth_headers_no_token(self):
        client = self._make_client()
        assert client._get_auth_headers() == {}

    def test_from_client_preserves_type(self):
        parent = self._make_client()
        child = AuthenticatedClient.from_client(parent)
        assert isinstance(child, AuthenticatedClient)

    def test_from_client_shares_auth(self):
        parent = self._make_client()
        child = AuthenticatedClient.from_client(parent)
        assert child._auth is parent._auth

    @pytest.mark.anyio
    async def test_request_retries_once_after_401(self):
        user = User()
        auth_calls = 0
        data_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal auth_calls, data_calls
            path = request.url.path
            if path.startswith("/nonce"):
                return httpx.Response(200, json={"value": "test-nonce"})
            if path == "/auth":
                auth_calls += 1
                return httpx.Response(
                    200,
                    json={
                        "token": f"tok-{auth_calls}",
                        "expiry_ns": time.time_ns() + 3600 * 1_000_000_000,
                    },
                )
            if path == "/data":
                data_calls += 1
                if data_calls == 1:
                    return httpx.Response(401, json={"error": "expired"})
                return httpx.Response(200, json={"ok": True})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        httpx_client = httpx.AsyncClient(base_url="http://test", transport=transport)

        client = AuthenticatedClient(
            base_url="http://test",
            default_user=user,
            client=httpx_client,
        )
        # Pre-seed a "valid" token so _ensure_auth is a no-op on the first call.
        client._auth.token = "stale-token"
        client._auth.expiry_ns = time.time_ns() + 3600 * 1_000_000_000

        result = await client._request("GET", "/data")

        assert result == {"ok": True}
        assert auth_calls == 1
        assert data_calls == 2
        assert client._auth.token == "tok-1"

        await client.close()

    @pytest.mark.anyio
    async def test_anonymous_request_does_not_retry_on_401(self):
        backend = FakeAuthBackend()
        data_calls = 0

        def on_request(_: httpx.Request) -> httpx.Response:
            nonlocal data_calls
            data_calls += 1
            return httpx.Response(401, text="nope")

        # No default_user → request stays anonymous even with requires_auth=False.
        client = mock_client(backend, on_request)

        with pytest.raises(httpx.HTTPStatusError):
            await client._request("GET", "/public", requires_auth=False)

        assert backend.auth_calls == 0
        assert data_calls == 1

        await client.close()

    @pytest.mark.anyio
    async def test_optional_auth_request_authenticates_when_user_set(self):
        backend = FakeAuthBackend(token="tok-1")
        seen: list[str | None] = []

        def on_request(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("Authorization"))
            return httpx.Response(200, json={"ok": True})

        client = mock_client(backend, on_request, default_user=User())
        result = await client._request("GET", "/public", requires_auth=False)

        assert result == {"ok": True}
        assert backend.auth_calls == 1
        assert seen == ["Bearer tok-1"]

        await client.close()

    @pytest.mark.anyio
    async def test_optional_auth_uses_kwarg_user_when_no_default(self):
        kwarg_user = User()
        backend = FakeAuthBackend(token="tok-kwarg")
        seen_user_id: list[str | None] = []

        def on_request(request: httpx.Request) -> httpx.Response:
            seen_user_id.append(request.headers.get("User-Id"))
            return httpx.Response(200, json={"ok": True})

        client = mock_client(backend, on_request)
        result = await client._request("GET", "/public", requires_auth=False, user=kwarg_user)

        assert result == {"ok": True}
        assert backend.auth_calls == 1
        assert backend.nonce_users == [kwarg_user.public_key]
        assert seen_user_id == [kwarg_user.public_key]

        await client.close()

    @pytest.mark.anyio
    async def test_optional_auth_ignores_bare_public_key_kwarg(self):
        # A bare UserPublicKey can't sign — stay anonymous, don't attempt auth.
        backend = FakeAuthBackend()
        seen: list[str | None] = []

        def on_request(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("Authorization"))
            return httpx.Response(200, json={"ok": True})

        client = mock_client(backend, on_request)
        result = await client._request(
            "GET", "/public", requires_auth=False, user=UserPublicKey("ab" * 32)
        )

        assert result == {"ok": True}
        assert backend.auth_calls == 0
        assert seen == [None]

        await client.close()

    @pytest.mark.anyio
    async def test_optional_auth_falls_back_anonymously_when_auth_fails(self, caplog):
        backend = FakeAuthBackend(auth_fail_after=0)
        seen: list[str | None] = []

        def on_request(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("Authorization"))
            return httpx.Response(200, json={"ok": True})

        client = mock_client(backend, on_request, default_user=User())

        with caplog.at_level(logging.ERROR, logger="tplus"):
            result = await client._request("GET", "/public", requires_auth=False)

        assert result == {"ok": True}
        assert seen == [None]
        assert any("anonymous" in record.message.lower() for record in caplog.records), caplog.text

        await client.close()

    @pytest.mark.anyio
    async def test_required_auth_failure_still_raises(self):
        backend = FakeAuthBackend(auth_fail_after=0)
        endpoint_hits = 0

        def on_request(_: httpx.Request) -> httpx.Response:
            nonlocal endpoint_hits
            endpoint_hits += 1
            return httpx.Response(200, json={"ok": True})

        client = mock_client(backend, on_request, default_user=User())

        with pytest.raises(httpx.HTTPStatusError):
            await client._request("GET", "/private")

        assert endpoint_hits == 0

        await client.close()

    @pytest.mark.anyio
    async def test_optional_auth_falls_back_when_refresh_fails_after_401(self, caplog):
        # Initial auth ok; server then 401s; refresh fails → anonymous retry.
        backend = FakeAuthBackend(token="tok-1", auth_fail_after=1)
        seen: list[str | None] = []
        data_calls = 0

        def on_request(request: httpx.Request) -> httpx.Response:
            nonlocal data_calls
            data_calls += 1
            seen.append(request.headers.get("Authorization"))
            if data_calls == 1:
                return httpx.Response(401, text="expired")

            return httpx.Response(200, json={"ok": True})

        client = mock_client(backend, on_request, default_user=User())

        with caplog.at_level(logging.ERROR, logger="tplus"):
            result = await client._request("GET", "/public", requires_auth=False)

        assert result == {"ok": True}
        assert seen == ["Bearer tok-1", None]
        assert any("anonymous" in record.message.lower() for record in caplog.records), caplog.text

        await client.close()

    @pytest.mark.anyio
    async def test_open_ws_authenticates_when_user_set(self, monkeypatch):
        user = User()
        client = AuthenticatedClient(base_url="http://test", default_user=user)
        client._auth.token = "tok-ws"
        client._auth.expiry_ns = time.time_ns() + 3600 * 1_000_000_000

        captured: dict = {}

        async def fake_super_open_ws(self, path, ws_kwargs=None, extra_headers=None, **kwargs):
            captured["extra_headers"] = extra_headers
            return object()

        monkeypatch.setattr(BaseClient, "_open_ws", fake_super_open_ws)

        await client._open_ws("/stream", requires_auth=False)

        headers = captured["extra_headers"]
        assert headers["Authorization"] == "Bearer tok-ws"
        assert headers["User-Id"] == user.public_key

        await client.close()

    @pytest.mark.anyio
    async def test_open_ws_anonymous_when_no_user(self, monkeypatch):
        client = AuthenticatedClient(base_url="http://test")

        captured: dict = {}

        async def fake_super_open_ws(self, path, ws_kwargs=None, extra_headers=None, **kwargs):
            captured["extra_headers"] = extra_headers
            return object()

        monkeypatch.setattr(BaseClient, "_open_ws", fake_super_open_ws)

        await client._open_ws("/stream", requires_auth=False)

        headers = captured["extra_headers"] or {}
        assert "Authorization" not in headers

        await client.close()

    @pytest.mark.anyio
    async def test_open_ws_falls_back_when_auth_fails(self, monkeypatch, caplog):
        user = User()
        client = AuthenticatedClient(base_url="http://test", default_user=user)

        async def fail_ensure_auth(user=None):
            raise RuntimeError("auth service down")

        monkeypatch.setattr(client, "_ensure_auth", fail_ensure_auth)

        captured: dict = {}

        async def fake_super_open_ws(self, path, ws_kwargs=None, extra_headers=None, **kwargs):
            captured["extra_headers"] = extra_headers
            return object()

        monkeypatch.setattr(BaseClient, "_open_ws", fake_super_open_ws)

        with caplog.at_level(logging.ERROR, logger="tplus"):
            await client._open_ws("/stream", requires_auth=False)

        headers = captured["extra_headers"] or {}
        assert "Authorization" not in headers
        assert any("anonymous" in record.message.lower() for record in caplog.records), caplog.text

        await client.close()

    @pytest.mark.anyio
    async def test_failed_authenticate_clears_stale_token(self):
        # A failed refresh must drop the cached bearer; otherwise the next call
        # would blindly resend a token the server is already rejecting.
        backend = FakeAuthBackend(nonce_fail_through=999, auth_fail_after=0)
        client = mock_client(backend, default_user=User())
        client._auth.token = "stale-token"
        client._auth.expiry_ns = time.time_ns() + 3600 * 1_000_000_000

        with pytest.raises(httpx.HTTPStatusError):
            await client._authenticate()

        assert client._auth.token is None
        assert client._auth.expiry_ns == 0

        await client.close()

    @pytest.mark.anyio
    async def test_auth_headers_persist_across_calls_with_valid_token(self):
        backend = FakeAuthBackend(token="tok-stable")
        seen: list[str | None] = []

        def on_request(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("Authorization"))
            return httpx.Response(200, json={"ok": True})

        client = mock_client(backend, on_request, default_user=User())

        await client._request("GET", "/a")
        await client._request("GET", "/b")
        await client._request("GET", "/c", requires_auth=False)

        assert seen == ["Bearer tok-stable"] * 3

        await client.close()

    @pytest.mark.anyio
    async def test_auth_headers_refresh_with_new_token_on_401(self):
        # 401 retry replaces the bearer; the rejected token must not linger.
        backend = FakeAuthBackend(token=lambda i: f"tok-{i}")
        seen: list[str | None] = []

        def on_request(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("Authorization"))
            if len(seen) == 2:
                return httpx.Response(401, text="token expired")

            return httpx.Response(200, json={"ok": True})

        client = mock_client(backend, on_request, default_user=User())

        await client._request("GET", "/data")
        await client._request("GET", "/data")
        await client._request("GET", "/data")

        # tok-1, tok-1 (rejected), tok-2 (401 retry), tok-2 (third call).
        assert seen == ["Bearer tok-1", "Bearer tok-1", "Bearer tok-2", "Bearer tok-2"]
        assert client._auth.token == "tok-2"

        await client.close()

    @pytest.mark.anyio
    async def test_anonymous_fallback_does_not_persist_to_next_call(self):
        # Fallback is per-call: once auth recovers, the next call re-auths.
        backend = FakeAuthBackend(token="tok-recovered", nonce_fail_through=1)
        seen: list[str | None] = []

        def on_request(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("Authorization"))
            return httpx.Response(200, json={"ok": True})

        client = mock_client(backend, on_request, default_user=User())
        await client._request("GET", "/public", requires_auth=False)
        await client._request("GET", "/public", requires_auth=False)

        assert seen == [None, "Bearer tok-recovered"]
        assert client._auth.token == "tok-recovered"

        await client.close()


class TestClientSettings:
    def test_defaults(self):
        settings = ClientSettings()
        assert settings.base_url == "http://localhost:3032"
        assert settings.timeout == 10.0
        assert settings.insecure_ssl is False
        assert settings.verify_requests is True

    def test_insecure_ssl(self):
        settings = ClientSettings(insecure_ssl=True)
        assert settings.verify_requests is False

    def test_parsed_base_url(self):
        settings = ClientSettings(base_url="https://api.example.com:8080")
        parsed = settings.parsed_base_url
        assert parsed.scheme == "https"
        assert parsed.hostname == "api.example.com"
        assert parsed.port == 8080

    def test_custom_headers(self):
        settings = ClientSettings(headers={"X-Custom": "value"})
        assert settings.headers == {"X-Custom": "value"}

    def test_from_url(self):
        settings = ClientSettings.from_url("http://example.com", insecure_ssl=True)
        assert settings.base_url == "http://example.com"
        assert settings.insecure_ssl is True
