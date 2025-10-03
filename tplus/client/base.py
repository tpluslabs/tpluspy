import json
import logging
import ssl
from collections.abc import AsyncIterator, Callable
from typing import Any
from urllib.parse import urlparse

import httpx
import websockets

from tplus.logger import get_logger
from tplus.utils.user import User


class BaseClient:
    """
    Base client to use across T+ services.
    """

    DEFAULT_TIMEOUT = 10.0
    AUTH = True

    def __init__(
        self,
        user: User,
        base_url: str,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | None = None,
        websocket_kwargs: dict[str, Any] | None = None,
        log_level: int = logging.INFO,
    ):
        self.user = user
        self.base_url = base_url.rstrip("/")
        self._parsed_base_url = urlparse(self.base_url)
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            verify=False,  # TODO remove that for production
        )
        self._ws_kwargs: dict[str, Any] = websocket_kwargs or {}

        import asyncio

        self._auth_lock: asyncio.Lock = asyncio.Lock()
        self._auth_token: str | None = None
        self._auth_expiry_ns: int = 0
        self.logger = get_logger(log_level=log_level)

    @classmethod
    def from_client(cls, client: "BaseClient"):
        """
        Easy way to clone clients without initializing multiple AsyncClients.
        """
        return cls(client.user, client.base_url, client=client._client)

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

        if self.AUTH and (
            not relative_url.startswith("/nonce") and not relative_url.startswith("/auth")
        ):
            await self._ensure_auth()

        try:
            if json_data or params:
                self.logger.debug(
                    f"Request to {method} {relative_url} with payload: {json_data} params: {params}"
                )
            request_headers = self._get_auth_headers()
            if request_headers:
                merged_headers = {**self._client.headers, **request_headers}
            else:
                merged_headers = None

            response = await self._client.request(  # type: ignore
                method=method,
                url=relative_url,
                json=json_data,
                params=params,
                headers=merged_headers,
            )

            # If we receive an HTTP 401/403, the auth token may have expired. Refresh the
            # credentials **once** and retry the request automatically. This keeps the
            # higher-level client APIs unaware of token lifetimes and greatly simplifies
            # consumer code.
            if response.status_code in {401, 403} and not relative_url.startswith("/auth"):
                self.logger.info(
                    "Received %s for %s – refreshing auth token and retrying once.",
                    response.status_code,
                    relative_url,
                )

                # Force re-authentication and rebuild the auth headers (inside the same
                # lock to avoid a thundering herd when many coroutines hit expiry at the
                # same time).
                await self._authenticate()
                retry_headers = {**self._client.headers, **self._get_auth_headers()}

                response = await self._client.request(  # type: ignore
                    method=method,
                    url=relative_url,
                    json=json_data,
                    params=params,
                    headers=retry_headers,
                )

            if response.status_code == 204:
                return {}
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

            except Exception:
                raise Exception(
                    f"Invalid response from server - status_code={response.status_code}."
                )

        except httpx.TimeoutException as e:
            self.logger.error(f"Request timed out to {e.request.url!r}: {e}")
            raise
        except httpx.RequestError as e:
            self.logger.error(
                f"An error occurred while requesting {e.request.url!r}: {type(e).__name__} - {e}"
            )
            raise
        except httpx.HTTPStatusError as e:
            self.logger.error(
                f"HTTP error {e.response.status_code} while requesting {e.request.url!r}: {e.response.text}"
            )
            raise
        except json.JSONDecodeError as e:
            self.logger.error(
                f"Failed to decode JSON response from {response.request.url!r}. Status: {response.status_code}. Content: {response.text[:100]}..."
            )
            raise ValueError(f"Invalid JSON received from API: {e}") from e

    async def _ensure_auth(self) -> None:
        import time

        safety_margin_ns = 60 * 1_000_000_000
        if self._auth_token and (time.time_ns() + safety_margin_ns) < self._auth_expiry_ns:
            return

        async with self._auth_lock:
            if self._auth_token and (time.time_ns() + safety_margin_ns) < self._auth_expiry_ns:
                return

            await self._authenticate()

    def _get_auth_headers(self) -> dict[str, str]:
        if not self._auth_token:
            return {}
        return {
            "Authorization": f"Bearer {self._auth_token}",
            "User-Id": self.user.public_key,
        }

    async def _authenticate(self) -> None:
        nonce_endpoint = f"/nonce/{self.user.public_key}"
        nonce_resp = await self._client.get(nonce_endpoint)  # type: ignore
        nonce_resp.raise_for_status()
        nonce_data = nonce_resp.json() if hasattr(nonce_resp, "json") else nonce_resp

        # NOTE: nonce_value **must** be a `str` here.
        nonce_value = f"{nonce_data['value']}" if isinstance(nonce_data, dict) else f"{nonce_data}"

        signature_bytes = self.user.sign(nonce_value)
        signature_array = list(signature_bytes)
        nonce_value_len = len(nonce_value)  # type: ignore

        self.logger.debug(f"AUTH DEBUG: nonce={nonce_value} (len={nonce_value_len})")
        self.logger.debug(
            f"AUTH DEBUG: signature={signature_array[:8]}... (len={len(signature_array)})"
        )

        auth_payload = {
            "user_id": self.user.public_key,
            "nonce": nonce_value,
            "signature": signature_array,
        }

        token_resp = await self._client.post("/auth", json=auth_payload)  # type: ignore
        token_resp.raise_for_status()
        token_json = token_resp.json() if hasattr(token_resp, "json") else token_resp

        self.logger.info(f"Full authentication response from server: {token_json}")
        token = token_json.get("token")  # type: ignore
        expiry_ns = int(token_json["expiry_ns"])  # type: ignore

        self.logger.debug(f"AUTH DEBUG: token={token} expires={expiry_ns} (len={len(token)})")

        self._auth_token = token_json["token"]  # type: ignore
        self._auth_expiry_ns = expiry_ns

    async def _ws_auth_headers(self) -> dict[str, str]:
        if self.AUTH:
            await self._ensure_auth()

        return self._get_auth_headers()

    def _get_websocket_url(self, path: str) -> str:
        from urllib.parse import urlunparse

        scheme = "wss" if self._parsed_base_url.scheme == "https" else "ws"
        netloc = self._parsed_base_url.netloc
        ws_path = path if path.startswith("/") else f"/{path}"
        return urlunparse((scheme, netloc, ws_path, "", "", ""))

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
        auth_headers = await self._ws_auth_headers()
        ws_kwargs = dict(self._ws_kwargs)
        if "extra_headers" in ws_kwargs and ws_kwargs["extra_headers"]:
            caller_headers = ws_kwargs.pop("extra_headers")
            if isinstance(caller_headers, dict):
                caller_headers.update(auth_headers)
                ws_kwargs["extra_headers"] = caller_headers
            else:
                ws_kwargs["extra_headers"] = list(auth_headers.items()) + list(caller_headers)
        else:
            ws_kwargs["extra_headers"] = auth_headers

        # TODO Remove this when we have a real SSL certificate (or make it configurable)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        async with websockets.connect(ws_url, **ws_kwargs, ssl=ssl_context) as websocket:
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
