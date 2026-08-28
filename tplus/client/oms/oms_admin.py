from tplus.client.auth import AuthenticatedClient
from tplus.model.asset_identifier import AssetIdentifier


class OmsAdminClient(AuthenticatedClient):
    async def set_settings(
        self,
        solvency_verifier: str,
        auto_reduce_enabled: bool,
        interest_reservation_enabled: bool | None = None,
        liquidation_monitor_enabled: bool | None = None,
        attached_bracket_budget_check_enabled: bool | None = None,
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
