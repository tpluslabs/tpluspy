import asyncio
import time
from typing import TYPE_CHECKING, Any

from typing_extensions import Self

from tplus.client.base import BaseClient
from tplus.utils.user import User

if TYPE_CHECKING:
    from tplus.types import UserType


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

    def __init__(
        self,
        base_url: str = "http://localhost:3032",
        *,
        auth: Auth | None = None,
        **kwargs,
    ):
        super().__init__(base_url, **kwargs)
        self._auth = auth or Auth()

    @classmethod
    def from_client(cls, client: "BaseClient") -> Self:
        auth = client._auth if isinstance(client, AuthenticatedClient) else None
        return cls.from_settings(
            client._settings,
            default_user=client._default_user,
            client=client._client,
            auth=auth,
        )

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        *,
        requires_auth: bool = True,
        user: "UserType | None" = None,
        request_timeout: float | None = None,
    ) -> dict[str, Any]:
        relative_url = endpoint if endpoint.startswith("/") else f"/{endpoint}"

        # Sign in opportunistically so authed callers get the higher-tier rate
        # limits even on endpoints flagged requires_auth=False.
        auth_user = self._auth_user_for(user)
        use_auth = requires_auth or auth_user is not None

        if use_auth and not relative_url.startswith(("/nonce", "/auth")):
            try:
                await self._ensure_auth(user=auth_user)
            except Exception as err:
                if requires_auth:
                    raise

                self.logger.error(
                    "Auth failed for %s %s (%s); falling back to anonymous.",
                    method,
                    relative_url,
                    err,
                )
                use_auth = False

        headers = self._build_headers(with_auth=use_auth, user=auth_user)
        response = await self._send(
            method,
            relative_url,
            json_data=json_data,
            params=params,
            headers=headers,
            request_timeout=request_timeout,
        )

        if use_auth and response.status_code in {401, 403} and not relative_url.startswith("/auth"):
            self.logger.info(
                "Received %s for %s – refreshing auth token and retrying once.",
                response.status_code,
                relative_url,
            )
            try:
                await self._authenticate(user=auth_user)
            except Exception as err:
                if requires_auth:
                    raise

                self.logger.error(
                    "Auth refresh failed for %s %s (%s); falling back to anonymous.",
                    method,
                    relative_url,
                    err,
                )
                use_auth = False

            headers = self._build_headers(with_auth=use_auth, user=auth_user)
            response = await self._send(
                method,
                relative_url,
                json_data=json_data,
                params=params,
                headers=headers,
                request_timeout=request_timeout,
            )

        return self._handle_response(response)

    def _auth_user_for(self, user: "UserType | None") -> "User | None":
        # Bare public-key strings can't sign; only User instances can.
        if isinstance(user, User):
            return user

        return self._default_user

    def _build_headers(self, *, with_auth: bool, user: "UserType | None" = None) -> dict[str, str]:
        headers = dict(self._settings.headers)
        if with_auth:
            headers.update(self._get_auth_headers(user=user))

        return headers

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
        # Clear up-front so a failed handshake leaves a clean "no token" state.
        self._auth.token = None
        self._auth.expiry_ns = 0

        user = self._resolve_user(user=user)
        nonce_endpoint = f"/nonce/{user.public_key}"
        nonce_resp = await self._client.get(nonce_endpoint)
        nonce_resp.raise_for_status()
        nonce_data = nonce_resp.json() if hasattr(nonce_resp, "json") else nonce_resp

        # NOTE: nonce_value **must** be a `str` here.
        nonce_value = f"{nonce_data['value']}" if isinstance(nonce_data, dict) else f"{nonce_data}"

        signature_bytes = user.sign(nonce_value)
        signature_array = list(signature_bytes)
        nonce_value_len = len(nonce_value)

        self.logger.debug(f"AUTH DEBUG: nonce={nonce_value} (len={nonce_value_len})")
        self.logger.debug(
            f"AUTH DEBUG: signature={signature_array[:8]}... (len={len(signature_array)})"
        )

        auth_payload = {
            "user_id": user.public_key,
            "nonce": nonce_value,
            "signature": signature_array,
        }

        token_resp = await self._client.post("/auth", json=auth_payload)
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

    async def _ws_auth_headers(self, user: "User | None" = None) -> dict[str, str]:
        await self._ensure_auth(user=user)
        return self._get_auth_headers(user=user)

    async def _open_ws(
        self,
        path: str,
        ws_kwargs: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        *,
        requires_auth: bool = True,
        user: "UserType | None" = None,
    ):
        auth_user = self._auth_user_for(user)
        use_auth = requires_auth or auth_user is not None
        if use_auth:
            try:
                auth_headers = await self._ws_auth_headers(user=auth_user)
                extra_headers = {**auth_headers, **(extra_headers or {})}
            except Exception as err:
                if requires_auth:
                    raise

                self.logger.error(
                    "WS auth failed for %s (%s); falling back to anonymous.", path, err
                )

        return await super()._open_ws(
            path,
            ws_kwargs=ws_kwargs,
            extra_headers=extra_headers,
            requires_auth=requires_auth,
            user=user,
        )
