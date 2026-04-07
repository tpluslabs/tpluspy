import asyncio
import time

import httpx
import pytest

from tplus.client.auth import Auth, AuthenticatedClient
from tplus.client.base import BaseClient, ClientSettings
from tplus.exceptions import MissingClientUserError
from tplus.model.types import UserPublicKey


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
    def _make_client(self, **settings_kwargs) -> BaseClient:
        return BaseClient(ClientSettings(**settings_kwargs))

    def test_constructor_with_settings(self):
        client = self._make_client(base_url="http://localhost:9999")
        assert isinstance(client._client, httpx.AsyncClient)
        assert client._settings.base_url == "http://localhost:9999"

    def test_constructor_with_url_string(self):
        client = BaseClient("http://localhost:9999")
        assert client._settings.base_url == "http://localhost:9999"

    def test_from_client_shares_internals(self):
        parent = self._make_client()
        child = BaseClient.from_client(parent)
        assert child._client is parent._client
        assert child._settings is parent._settings

    def test_validate_user_with_no_default_raises(self):
        client = self._make_client()
        with pytest.raises(MissingClientUserError):
            client._validate_user()

    def test_validate_user_returns_default(self):
        class FakeUser:
            public_key = "abc"

        client = BaseClient(ClientSettings(), default_user=FakeUser())  # type: ignore
        assert client._validate_user().public_key == "abc"  # type: ignore

    def test_validate_user_prefers_explicit(self):
        class FakeUser:
            public_key = "abc"

        class OtherUser:
            public_key = "xyz"

        client = BaseClient(ClientSettings(), default_user=FakeUser())  # type: ignore
        assert client._validate_user(user=OtherUser()).public_key == "xyz"  # type: ignore

    def test_validate_user_public_key_from_string(self):
        key = UserPublicKey("ab" * 32)
        client = BaseClient(ClientSettings())
        assert client._validate_user_public_key(key) == key

    def test_validate_user_public_key_from_user(self):
        from tplus.utils.user import User

        user = User()
        client = BaseClient(ClientSettings())
        assert client._validate_user_public_key(user) == user.public_key

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
        return AuthenticatedClient(ClientSettings(), default_user=default_user, auth=auth)

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
