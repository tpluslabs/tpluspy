import time
from typing import TYPE_CHECKING

from tplus.client.auth import AuthenticatedClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.sync_book import CreateSyncBookResponse
from tplus.utils.operator import load_operator_sk, sign_operator_payload
from tplus.utils.user import to_user_public_key

if TYPE_CHECKING:
    from tplus.types import UserType


def canonical_asset_id(asset_id: int | AssetIdentifier | str) -> str:
    """``asset_id`` as the OMS prints it: a registry index in decimal, or a lowercase
    32-byte address ``@`` its lowercase 9-byte chain. The OMS verifies an operator
    signature over this form, whatever spelling the request carried.
    """
    asset = AssetIdentifier(asset_id) if not isinstance(asset_id, AssetIdentifier) else asset_id
    if asset.indexed:
        return str(int(asset.root))
    return asset.root.lower()


class OmsAdminClient(AuthenticatedClient):
    async def create_sync_book(
        self,
        user: "UserType",
        asset_id: int | AssetIdentifier | str,
        operator_secret: str,
        timestamp_ns: int | None = None,
        nonce: int | None = None,
    ) -> CreateSyncBookResponse:
        """Create a market maker's sync book on one market (``POST /admin/sync-book``).

        Signed with the OMS operator key, so the market maker does not have to call
        ``POST /sync_book/create`` itself. ``user`` must be a registered market maker. The
        reply says whether the book was ``CREATED`` or ``ALREADY_EXISTED``; a new book also
        sends the market maker a ``SyncBookCreated`` account event.
        """
        ts = time.time_ns() if timestamp_ns is None else timestamp_ns
        request_nonce = time.time_ns() if nonce is None else nonce
        user_id = to_user_public_key(user)
        asset = canonical_asset_id(asset_id)
        payload = (
            b"oms.admin.create_sync_book.v1"
            + request_nonce.to_bytes(8, "big")
            + ts.to_bytes(8, "big")
            + bytes.fromhex(user_id)
            + asset.encode()
        )
        signature = sign_operator_payload(payload, load_operator_sk(operator_secret))
        resp = await self._post(
            "admin/sync-book",
            json_data={
                "inner": {
                    "timestamp_ns": ts,
                    "nonce": request_nonce,
                    "asset_id": asset,
                    "user_id": user_id,
                },
                "signature": signature,
            },
            requires_auth=False,
        )
        return CreateSyncBookResponse.model_validate(resp)

    async def list_suspended_withdrawals(self) -> dict:
        """Every user whose withdrawals the clearing engine has suspended, oldest first.

        Each entry carries ``suspended_since_ns`` and ``inventory``: the user's whole
        inventory as it stood when the suspension was raised, in the shape of
        ``GET /inventory/user/{user_id}`` (``None`` until the CE's gossip of it lands).
        """
        return await self._get("admin/withdrawal/suspended", requires_auth=False)

    async def set_settings(
        self,
        solvency_verifier: str,
        auto_reduce_enabled: bool,
        interest_reservation_enabled: bool | None = None,
        liquidation_monitor_enabled: bool | None = None,
        attached_bracket_budget_check_enabled: bool | None = None,
        preflight_enabled: bool | None = None,
    ):
        config = {
            "solvency_verifier": solvency_verifier,
            "auto_reduce_enabled": auto_reduce_enabled,
        }
        if interest_reservation_enabled is not None:
            config["interest_reservation_enabled"] = interest_reservation_enabled
        if liquidation_monitor_enabled is not None:
            config["liquidation_monitor_enabled"] = liquidation_monitor_enabled
        if attached_bracket_budget_check_enabled is not None:
            config["attached_bracket_budget_check_enabled"] = attached_bracket_budget_check_enabled
        if preflight_enabled is not None:
            config["preflight_enabled"] = preflight_enabled

        await self._post(
            "admin/settings/modify",
            json_data=config,
        )

    async def get_impact_prices(self, asset_id: int | AssetIdentifier | str) -> dict:
        """Read the OMS's current impact prices for an asset (debug only).

        Returns ``{"buy_impact": {"price": str, "decimals": int} | None, "sell_impact": ...}``.
        Reflects the full pipeline: the orderbook computes the VWAP impact, publishes it to the
        CE, which propagates it to the OMS price manager (the prices market orders are sized on).
        """
        return await self._post(
            "admin/impact-prices/query",
            json_data={"asset_id": str(asset_id)},
        )

    async def set_order_failure_mode(
        self,
        order_id: str,
        mode: str,
        delay_ms: int | None = None,
    ):
        """Inject a per-order failure mode, applied when the order is submitted (debug only).

        Must be called BEFORE creating the order; keyed by the same ``order_id``. The mode is
        consumed the first time that order is submitted.

        - ``mode="slow"``: delay the OMS submission by ``delay_ms`` before forwarding to the OB.
        - ``mode="lose"``: drop the order between OMS and OB (never forwarded); the OMS waits out
          the orderbook-confirmation timeout.
        """
        payload: dict = {"order_id": order_id, "mode": mode}
        if mode == "slow":
            if delay_ms is None:
                raise ValueError("delay_ms is required when mode='slow'")
            payload["delay_ms"] = delay_ms

        await self._post(
            "admin/order-failure-mode/set",
            json_data=payload,
        )

    async def force_auto_reduce_now(
        self,
        user_id: str,
        sub_account: int,
        asset_id: int | AssetIdentifier | str,
    ):
        if isinstance(asset_id, AssetIdentifier):
            serialized_asset_id = str(asset_id)
        elif isinstance(asset_id, int):
            serialized_asset_id = str(asset_id)
        else:
            serialized_asset_id = asset_id

        await self._post(
            "admin/auto-reduce/force-run",
            json_data={
                "user_id": user_id,
                "sub_account": sub_account,
                "asset_id": serialized_asset_id,
            },
        )

    async def freeze_clock(self, now_ns: int | None = None) -> dict:
        """Pin the OMS's clock to ``now_ns``, or release it with ``None`` (debug only).

        Each service holds its own clock, so a scenario that pins time has to pin the
        clearing engine's and the orderbook's too. Returns ``{"frozen_at_ns", "now_ns"}``.
        """
        return await self._post("admin/clock", json_data={"now_ns": now_ns})

    async def get_clock(self) -> dict:
        """Whether the OMS's clock is pinned, and to what (debug only)."""
        return await self._get("admin/clock")
