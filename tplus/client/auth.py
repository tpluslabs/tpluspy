import asyncio
import time
from typing import TYPE_CHECKING, Any

from tplus.client.base import BaseClient

if TYPE_CHECKING:
    from tplus.types import UserType
    from tplus.utils.user import User


class Auth:
    SAFETY_MARGIN_NS = 60 * 1_000_000_000

    def __init__(self, token: str | None = None) -> None:
        self.lock = asyncio.Lock()
        self.token = token
        self.expiry_ns = 0

    def is_expired(self) -> bool:
        if self.token and (time.time_ns() + self.SAFETY_MARGIN_NS) < self.expiry_ns:
            return False
        return True


class AuthenticatedClient(BaseClient):
    """
    A BaseClient that adds token-based authentication.
    """

    def __init__(self, *args, auth: Auth | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._auth = auth or Auth()

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        relative_url = endpoint if endpoint.startswith("/") else f"/{endpoint}"

        if not relative_url.startswith("/nonce") and not relative_url.startswith("/auth"):
            await self._ensure_auth()

        response = await self._send(method, relative_url, json_data=json_data, params=params)

        # If we receive an HTTP 401/403, the auth token may have expired. Refresh the
        # credentials **once** and retry the request automatically.
        if response.status_code in {401, 403} and not relative_url.startswith("/auth"):
            self.logger.info(
                "Received %s for %s – refreshing auth token and retrying once.",
                response.status_code,
                relative_url,
            )
            await self._authenticate()
            response = await self._send(method, relative_url, json_data=json_data, params=params)

        return self._handle_response(response)

    def _get_request_headers(self) -> dict[str, str]:
        headers = super()._get_request_headers()
        headers.update(self._get_auth_headers())
        return headers

    def _get_auth_headers(self, user: "UserType | None" = None) -> dict[str, str]:
        if not self._auth.token:
            return {}

        return {
            "Authorization": f"Bearer {self._auth.token}",
            "User-Id": self._validate_user_public_key(user=user),
        }

    async def _ensure_auth(self, user: "User | None" = None) -> None:
        if not self._auth.is_expired():
            return

        async with self._auth.lock:
            if not self._auth.is_expired():
                return

            await self._authenticate(user=user)

    async def _authenticate(self, user: "User | None" = None) -> None:
        user = user or self._validate_user(user=user)
        nonce_endpoint = f"/nonce/{user.public_key}"
        nonce_resp = await self._client.get(nonce_endpoint)  # type: ignore
        nonce_resp.raise_for_status()
        nonce_data = nonce_resp.json() if hasattr(nonce_resp, "json") else nonce_resp

        # NOTE: nonce_value **must** be a `str` here.
        nonce_value = f"{nonce_data['value']}" if isinstance(nonce_data, dict) else f"{nonce_data}"

        signature_bytes = user.sign(nonce_value)
        signature_array = list(signature_bytes)
        nonce_value_len = len(nonce_value)  # type: ignore

        self.logger.debug(f"AUTH DEBUG: nonce={nonce_value} (len={nonce_value_len})")
        self.logger.debug(
            f"AUTH DEBUG: signature={signature_array[:8]}... (len={len(signature_array)})"
        )

        auth_payload = {
            "user_id": user.public_key,
            "nonce": nonce_value,
            "signature": signature_array,
        }

        token_resp = await self._client.post("/auth", json=auth_payload)  # type: ignore
        token_resp.raise_for_status()
        token_json = token_resp.json() if hasattr(token_resp, "json") else token_resp

        token = token_json.get("token")  # type: ignore
        expiry_ns = int(token_json["expiry_ns"])  # type: ignore

        # Mask token if present
        if isinstance(token, str):
            masked = token[:4] + "…" + token[-4:] if len(token) >= 8 else "***"
        else:
            masked = "***"
        self.logger.debug(f"AUTH DEBUG: token={masked} expires={expiry_ns}")

        self._auth.token = token_json["token"]  # type: ignore
        self._auth.expiry_ns = expiry_ns

    async def _ws_auth_headers(self) -> dict[str, str]:
        await self._ensure_auth()
        return self._get_auth_headers()

    async def _open_ws(
        self,
        path: str,
        ws_kwargs: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ):
        auth_headers = await self._ws_auth_headers()
        extra_headers = {**auth_headers, **(extra_headers or {})}
        return await super()._open_ws(path, ws_kwargs=ws_kwargs, extra_headers=extra_headers)
