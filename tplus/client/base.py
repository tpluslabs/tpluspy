import json
import logging
import ssl
from collections.abc import AsyncIterator, Callable
from functools import cached_property
from typing import TYPE_CHECKING, Any, Self
from urllib.parse import urlparse

import httpx
import websockets
from pydantic import BaseModel

from tplus.exceptions import MissingClientUserError
from tplus.logger import get_logger
from tplus.utils.user import User

if TYPE_CHECKING:
    from tplus.model.types import UserPublicKey
    from tplus.types import UserType

DEFAULT_TIMEOUT = 10.0
DEFAULT_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


class ClientSettings(BaseModel):
    """
    Validated client settings.
    """

    base_url: str = "http://localhost:3032"
    """
    Base URL for requests.
    """

    timeout: float = DEFAULT_TIMEOUT
    """
    Requests timeout.
    """

    websocket_kwargs: dict[str, Any] = {}
    """
    Additional kwargs to pass to websocket requests.
    """

    insecure_ssl: bool = False
    """
    Set to to not verify SSL certificates.
    """

    headers: dict[str, Any] = DEFAULT_HEADERS
    """
    HTTP headers.
    """

    @classmethod
    def from_url(cls, url: str, **kwargs) -> "ClientSettings":
        return cls(base_url=url, **kwargs)

    @cached_property
    def parsed_base_url(self):
        return urlparse(self.base_url)

    @property
    def verify_requests(self) -> bool:
        return not self.insecure_ssl


def create_httpx_client(settings: ClientSettings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.base_url,
        timeout=settings.timeout,
        headers=settings.headers,
        verify=settings.verify_requests,
    )


class BaseClient:
    """
    Base client to use across T+ services.
    """

    def __init__(
        self,
        settings: ClientSettings | str,
        default_user: User | None = None,
        log_level: int = logging.INFO,
        client: httpx.AsyncClient | None = None,
        **kwargs,
    ):
        if isinstance(settings, str):
            settings = ClientSettings.from_url(settings)

        self._settings = settings
        self._default_user = default_user
        self._client = client or create_httpx_client(settings)
        self.logger = get_logger(log_level=log_level)

    @classmethod
    def from_client(cls, client: "BaseClient") -> Self:
        return cls(
            client._settings,
            default_user=client._default_user,
            client=client._client,
        )

    def _validate_user(self, user: User | None = None) -> User:
        if user is not None:
            return user

        elif self._default_user is None:
            raise MissingClientUserError()

        return self._default_user

    def _validate_user_public_key(self, user: "UserType | None" = None) -> "UserPublicKey":
        if user is not None:
            if isinstance(user, User):
                return user.public_key

            return user

        elif self._default_user is None:
            raise MissingClientUserError()

        return self._default_user.public_key

    async def _get(self, endpoint: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("GET", endpoint, json_data=json_data)

    async def _post(self, endpoint: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("POST", endpoint, json_data=json_data)

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        relative_url = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        response = await self._send(method, relative_url, json_data=json_data, params=params)
        return self._handle_response(response)

    def _get_request_headers(self) -> dict[str, str]:
        return dict(self._settings.headers)

    async def _send(
        self,
        method: str,
        relative_url: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        if json_data or params:
            self.logger.debug(
                f"Request to {method} {relative_url} with payload: {json_data} params: {params}"
            )

        merged_headers = self._get_request_headers()

        try:
            return await self._client.request(  # type: ignore
                method=method,
                url=relative_url,
                json=json_data,
                params=params,
                headers=merged_headers,
            )
        except httpx.TimeoutException as err:
            self.logger.error(f"Request timed out to {err.request.url!r}: {err}")
            raise

        except httpx.RequestError as err:
            self.logger.error(
                f"An error occurred while requesting {err.request.url!r}: {type(err).__name__} - {err}"
            )
            raise

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 204:
            return {}

        raise_for_status_with_body(response)

        if not response.content:
            return {}

        try:
            json_response = response.json()
            if json_response is None:
                self.logger.warning(
                    f"API endpoint {response.request.url!r} returned JSON null. Treating as empty dictionary."
                )
                return {}

            return json_response

        except json.JSONDecodeError as e:
            self.logger.error(
                f"Failed to decode JSON response from {response.request.url!r}. "
                f"Status: {response.status_code}. Content: {response.text[:100]}..."
            )
            raise ValueError(f"Invalid JSON received from API: {e}") from e

    def _get_websocket_url(self, path: str) -> str:
        from urllib.parse import urlunparse

        parsed = self._settings.parsed_base_url
        scheme = "wss" if parsed.scheme == "https" else "ws"
        netloc = parsed.netloc
        ws_path = path if path.startswith("/") else f"/{path}"
        return urlunparse((scheme, netloc, ws_path, "", "", ""))

    async def _open_ws(
        self,
        path: str,
        ws_kwargs: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ):
        """
        Build a WebSocket connection context for the given path with proper
        TLS/handshake settings. Returns a websockets.connect context manager.
        """
        ws_url = self._get_websocket_url(path)
        headers = extra_headers or {}

        final_kwargs = dict(self._settings.websocket_kwargs)
        if ws_kwargs:
            final_kwargs.update(ws_kwargs)

        # Merge extra headers with caller-provided headers
        if "extra_headers" in final_kwargs and final_kwargs["extra_headers"]:
            caller_headers = final_kwargs.pop("extra_headers")
            if isinstance(caller_headers, dict):
                caller_headers.update(headers)
                final_kwargs["extra_headers"] = caller_headers
            else:
                final_kwargs["extra_headers"] = list(headers.items()) + list(caller_headers)
        else:
            final_kwargs["extra_headers"] = headers

        parsed = self._settings.parsed_base_url

        # Provide Origin to be proxy/gateway friendly
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if "origin" not in final_kwargs:
            final_kwargs["origin"] = origin

        # Build SSL context (secure by default). Only set ALPN/server_hostname for HTTPS.
        if parsed.scheme == "https":
            ssl_context = ssl.create_default_context()
            if self._settings.insecure_ssl:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            try:
                ssl_context.set_alpn_protocols(["http/1.1"])  # avoid h2 for WS
            except Exception:
                pass

            server_hostname = parsed.hostname
            if server_hostname:
                return websockets.connect(
                    ws_url, **final_kwargs, ssl=ssl_context, server_hostname=server_hostname
                )
            return websockets.connect(ws_url, **final_kwargs, ssl=ssl_context)

        # Plain WS (no TLS)
        return websockets.connect(ws_url, **final_kwargs)

    CONTROL_MESSAGE_TYPES: set[str] = {
        "subscriptions",
        "ping",
        "pong",
    }

    async def _stream_ws(
        self,
        path: str,
        parser: Callable[[Any], Any],
        *,
        control_handler: Callable[[dict[str, Any]], None] | None = None,
    ) -> AsyncIterator[Any]:
        ws_url = self._get_websocket_url(path)
        self.logger.debug("Connecting to %s stream: %s", path, ws_url)
        websocket_cm = await self._open_ws(path)

        async with websocket_cm as websocket:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if isinstance(data, dict) and data.get("type") in self.CONTROL_MESSAGE_TYPES:
                        if control_handler is not None:
                            control_handler(data)
                        continue
                    yield parser(data)
                except json.JSONDecodeError:
                    self.logger.warning(
                        "Received non-JSON message on %s stream: %s…", path, message[:100]
                    )
                except Exception as e:
                    self.logger.error(
                        "Error processing message from %s stream: %s. Message: %s…",
                        path,
                        e,
                        message[:100],
                    )

    async def close(self) -> None:
        """
        Closes the underlying httpx async client.
        """
        self.logger.debug("Closing async HTTP client.")
        if self._client and isinstance(self._client, httpx.AsyncClient):
            await self._client.aclose()

    async def __aenter__(self):
        """
        Async context manager entry.
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit.
        """
        await self.close()


def raise_for_status_with_body(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as err:
        body = response.text.strip()
        msg = f"{err} | Response body: {body}" if body else str(err)
        raise httpx.HTTPStatusError(
            msg,
            request=err.request,
            response=err.response,
        ) from None
