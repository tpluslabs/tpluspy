import asyncio
import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from typing_extensions import Self

from tplus.client.base import BaseClient, WebSocketConnection, strip_query_from_path
from tplus.client.websocket import TplusWebSocket
from tplus.exceptions import is_unauthenticated_status
from tplus.model.auth import AuthRequestBody, AuthTokenResponse
from tplus.model.multisig import AdditionalSigner, SignerKey
from tplus.utils.user import User, to_user, token_cache

if TYPE_CHECKING:
    from tplus.types import UserLike, UserType


class AuthenticatedConnection(NamedTuple):
    """A WebSocket connection paired with the token its handshake actually presented."""

    connection: WebSocketConnection
    presented_token: str | None


class Auth:
    SAFETY_MARGIN_NS = 60 * 1_000_000_000

    def __init__(self, token: str | None = None, *, cache_dir: Path | None = None) -> None:
        self.lock = asyncio.Lock()
        self.token = token
        self.expiry_ns = 0
        self._cache_dir = cache_dir

    def is_expired(self) -> bool:
        if self.token and (time.time_ns() + self.SAFETY_MARGIN_NS) < self.expiry_ns:
            return False

        return True

    @property
    def cache_dir(self) -> Path | None:
        """Directory used for encrypted token caching, if configured."""
        return self._cache_dir

    def load_cached(self, pubkey: str, base_url: str, password: str) -> bool:
        if self._cache_dir is None:
            return False

        path = token_cache.cache_path(self._cache_dir, pubkey, base_url)
        if not path.is_file():
            return False

        try:
            blob = json.loads(path.read_text())
            if blob.get("base_url") != base_url:
                return False

            self.token = token_cache.decrypt(blob, password)
            self.expiry_ns = int(blob["expiry_ns"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            self.token = None
            self.expiry_ns = 0
            return False

        return not self.is_expired()

    def save_cached(self, pubkey: str, base_url: str, password: str) -> None:
        if self._cache_dir is None or not self.token:
            return

        try:
            blob = token_cache.encrypt(self.token, self.expiry_ns, base_url, password)
            path = token_cache.cache_path(self._cache_dir, pubkey, base_url)
            token_cache.write_atomic(path, blob)
        except OSError:
            pass


class AuthenticatedClient(BaseClient):
    """
    A BaseClient that adds token-based authentication.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:3032",
        *,
        auth: Auth | None = None,
        auth_path_prefix: str = "",
        auth_additional_signers: "Sequence[UserLike] | None" = None,
        **kwargs,
    ):
        super().__init__(base_url, **kwargs)
        self._auth = auth or Auth()
        prefix = auth_path_prefix.strip("/")
        self._auth_path_prefix = f"/{prefix}" if prefix else ""
        self._auth_additional_signers: list[User] = [
            to_user(signer) for signer in auth_additional_signers or []
        ]

    @classmethod
    def from_client(
        cls,
        client: "BaseClient",
        *,
        auth: Auth | None = None,
        auth_path_prefix: str | None = None,
        auth_additional_signers: "Sequence[UserLike] | None" = None,
    ) -> Self:
        if isinstance(client, AuthenticatedClient):
            auth = auth or client._auth
            if auth_path_prefix is None:
                auth_path_prefix = client._auth_path_prefix
            if auth_additional_signers is None:
                auth_additional_signers = client.auth_additional_signers

        return cls.from_settings(
            client._settings,
            default_user=client._default_user,
            client=client._client,
            auth=auth,
            auth_path_prefix=auth_path_prefix or "",
            auth_additional_signers=auth_additional_signers,
        )

    @property
    def auth_additional_signers(self) -> list[User]:
        """Cosigners included on every ``/auth`` handshake (master + these keys)."""
        return list(self._auth_additional_signers)

    def set_default_user(self, user: "UserLike | None") -> None:
        # The cached token belongs to the outgoing identity, so it cannot carry over.
        super().set_default_user(user)
        self._auth.token = None
        self._auth.expiry_ns = 0

    def _auth_endpoint(self, path: str) -> str:
        return f"{self._auth_path_prefix}/{path.lstrip('/')}"

    def _auth_cache_scope(self) -> str:
        if not self._auth_path_prefix:
            return self._settings.base_url
        return f"{self._settings.base_url.rstrip('/')}{self._auth_path_prefix}"

    def set_auth_additional_signers(self, signers: "Sequence[UserLike] | None") -> None:
        """Cosigners included on every `/auth` handshake (master + these keys).

        Required when the account's Low multisig threshold exceeds master weight.
        Clears the current token so the next request re-authenticates with the
        new signer set.
        """
        new_signers = [to_user(signer) for signer in signers or []]
        if new_signers == self._auth_additional_signers:
            return

        self._auth_additional_signers = new_signers
        self._auth.token = None
        self._auth.expiry_ns = 0

    async def authenticate(
        self,
        user: "User | None" = None,
        *,
        additional_signers: "Sequence[UserLike] | None" = None,
    ) -> None:
        """Force a fresh `/auth` handshake.

        If ``additional_signers`` is provided, replaces the client's auth cosigner
        set for this and future authentications.
        """
        if additional_signers is not None:
            self.set_auth_additional_signers(additional_signers)
        await self._authenticate(user=user)

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        *,
        requires_auth: bool = True,
        user: "UserType | None" = None,
        headers: dict[str, str] | None = None,
        request_timeout: float | None = None,
    ) -> dict[str, Any]:
        relative_url = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        extra_headers = headers

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
                    strip_query_from_path(relative_url),
                    err,
                )
                use_auth = False

        headers = self._build_headers(with_auth=use_auth, user=auth_user)
        if extra_headers:
            headers.update(extra_headers)

        presented_token = self._auth.token
        response = await self._send(
            method,
            relative_url,
            json_data=json_data,
            params=params,
            headers=headers,
            request_timeout=request_timeout,
        )

        if (
            use_auth
            and is_unauthenticated_status(response.status_code)
            and not relative_url.startswith("/auth")
        ):
            self.logger.info(
                "Received %s for %s, refreshing auth token and retrying once.",
                response.status_code,
                strip_query_from_path(relative_url),
            )
            try:
                await self._refresh_rejected_token(presented_token, user=auth_user)
            except Exception as err:
                if requires_auth:
                    raise

                self.logger.error(
                    "Auth refresh failed for %s %s (%s); falling back to anonymous.",
                    method,
                    strip_query_from_path(relative_url),
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
        # Bare public-key strings can't sign; only users and EVM accounts can.
        if user is None or isinstance(user, str):
            return self._default_user

        return self._resolve_user(user)

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

            if password := token_cache.resolve_cache_password():
                pubkey = self._resolve_user(user=user).public_key
                if self._auth.load_cached(pubkey, self._auth_cache_scope(), password):
                    return

            await self._authenticate(user=user)

    async def _authenticate(self, user: "User | None" = None) -> None:
        # Clear up-front so a failed handshake leaves a clean "no token" state.
        self._auth.token = None
        self._auth.expiry_ns = 0

        user = self._resolve_user(user=user)
        nonce_endpoint = self._auth_endpoint(f"nonce/{user.public_key}")
        nonce_resp = await self._client.get(nonce_endpoint)
        nonce_resp.raise_for_status()
        nonce_data = nonce_resp.json() if hasattr(nonce_resp, "json") else nonce_resp

        # NOTE: nonce_value **must** be a `str` here.
        nonce_value = f"{nonce_data['value']}" if isinstance(nonce_data, dict) else f"{nonce_data}"

        signature_array, additional_signers = user.signing_parts(nonce_value)
        nonce_value_len = len(nonce_value)

        self.logger.debug(f"AUTH DEBUG: nonce={nonce_value} (len={nonce_value_len})")
        self.logger.debug(
            f"AUTH DEBUG: signature={signature_array[:8]}... (len={len(signature_array)})"
        )

        if self._auth_additional_signers:
            additional_signers = [
                AdditionalSigner(
                    signer=SignerKey.ed25519(cosigner.public_key_vec),
                    signature=list(cosigner.sign(nonce_value)),
                )
                for cosigner in self._auth_additional_signers
            ]

        auth_payload = AuthRequestBody(
            user_id=user.public_key,
            nonce=nonce_value,
            signature=signature_array,
            additional_signers=additional_signers,
        )

        token_resp = await self._client.post(
            self._auth_endpoint("auth"),
            json=auth_payload.model_dump(mode="json"),
        )
        token_resp.raise_for_status()
        token_json = token_resp.json() if hasattr(token_resp, "json") else token_resp
        token_data = AuthTokenResponse.model_validate(token_json)

        token = token_data.token
        expiry_ns = token_data.expiry_ns

        # Mask token if present
        if isinstance(token, str):
            masked = token[:4] + "…" + token[-4:] if len(token) >= 8 else "***"
        else:
            masked = "***"

        self.logger.debug(f"AUTH DEBUG: token={masked} expires={expiry_ns}")

        self._auth.token = token
        self._auth.expiry_ns = expiry_ns

        if password := token_cache.resolve_cache_password():
            self._auth.save_cached(user.public_key, self._auth_cache_scope(), password)

    async def _refresh_rejected_token(
        self, rejected_token: str | None, user: "User | None" = None
    ) -> None:
        async with self._auth.lock:
            if self._auth.token != rejected_token:
                return

            await self._authenticate(user=user)

    async def _ws_auth_headers(self, user: "User | None" = None) -> dict[str, str]:
        await self._ensure_auth(user=user)
        return self._get_auth_headers(user=user)

    async def _connect_ws_with_auth(
        self,
        path: str,
        *,
        ws_kwargs: dict[str, Any] | None,
        caller_headers: dict[str, str] | None,
        requires_auth: bool,
        user: "UserType | None",
        auth_user: "User | None",
    ) -> AuthenticatedConnection:
        connection_headers = caller_headers
        try:
            auth_headers = await self._ws_auth_headers(user=auth_user)
            connection_headers = {**auth_headers, **(caller_headers or {})}
        except Exception as err:
            if requires_auth:
                raise

            self.logger.error("WS auth failed for %s (%s); falling back to anonymous.", path, err)

        # Read before the next await, so a concurrent refresh cannot swap it in between.
        presented_token = self._auth.token
        connection = await super()._open_ws(
            path,
            ws_kwargs=ws_kwargs,
            extra_headers=connection_headers,
            requires_auth=requires_auth,
            user=user,
        )
        return AuthenticatedConnection(connection, presented_token)

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
        if not use_auth:
            return await super()._open_ws(
                path,
                ws_kwargs=ws_kwargs,
                extra_headers=extra_headers,
                requires_auth=requires_auth,
                user=user,
            )

        connection, presented_token = await self._connect_ws_with_auth(
            path,
            ws_kwargs=ws_kwargs,
            caller_headers=extra_headers,
            requires_auth=requires_auth,
            user=user,
            auth_user=auth_user,
        )

        async def reconnect_after_rejection() -> WebSocketConnection:
            """Re-authenticate if nothing else already has, then rebuild the connection."""
            await self._refresh_rejected_token(presented_token, user=auth_user)
            retried, _ = await self._connect_ws_with_auth(
                path,
                ws_kwargs=ws_kwargs,
                caller_headers=extra_headers,
                requires_auth=requires_auth,
                user=user,
                auth_user=auth_user,
            )
            return retried

        return TplusWebSocket(connection, reconnect_after_rejection, self.logger, path)
