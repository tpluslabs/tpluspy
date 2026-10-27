import time
from typing import TYPE_CHECKING, Any, cast

from cryptography.hazmat.primitives.asymmetric import ec

from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.interest_rates import InterestRates
from tplus.model.representation_rate import SetRepresentationRateMappingRequest
from tplus.model.types import UserPublicKey
from tplus.model.vault import VaultBalance
from tplus.utils.operator import load_operator_sk, sign_operator_payload
from tplus.utils.serializers import to_u256_str
from tplus.utils.user import to_user_public_key

if TYPE_CHECKING:
    from tplus.types import UserType


class AdminClient(BaseClearingEngineClient):
    @staticmethod
    def _load_operator_sk(operator_secret) -> ec.EllipticCurvePrivateKey:
        return load_operator_sk(operator_secret)

    @staticmethod
    def _sign(payload: bytes, sk: ec.EllipticCurvePrivateKey) -> str:
        """SHA256 -> ECDSA sign -> low-S normalize -> compact r||s -> hex."""
        return sign_operator_payload(payload, sk)

    async def get_verifying_key(self):
        """
        Get a clearing-engine's verifying key.

        Returns:
            str | None
        """
        return await self._get("admin/verifying-key")

    async def get_latest_checkpoint_root(self) -> str | None:
        """
        Get the clearing-engine's latest locally completed checkpoint root.
        """
        response = await self._get("admin/checkpoint/root")
        return response.get("root")

    async def modify_user_inventory(
        self,
        user: "UserPublicKey",
        asset: "AssetIdentifier",
        base_balance: dict,
        quote_balance: dict,
        spot_balance: str,
        average_spot_deposit: str,
        sub_account_index: int = 1,
    ):
        """
        Admin-only API for testing.

        Args:
            user: The user's public key
            asset: The asset identifier
            balance: Dict with "credits" and "liabilities" keys
            sub_account_index: The sub-account index (0=main, 1=margin). Defaults to 1 (margin).
        """
        if not isinstance(user, UserPublicKey):
            user = UserPublicKey.__validate_user__(user)
        if not isinstance(asset, AssetIdentifier):
            asset = AssetIdentifier.model_validate(asset)

        asset = asset.model_dump()

        await self._post(
            "admin/inventory/modify",
            json_data={
                "user": user,
                "asset": asset,
                "balance": base_balance,
                "quote_balance": quote_balance,
                "spot": spot_balance,
                "average_spot_deposit": average_spot_deposit,
                "sub_account_index": sub_account_index,
            },
        )

    async def freeze_clock(self, now_ns: int | None = None) -> dict[str, Any]:
        """
        Admin-only API for testing: pin the clearing engine's clock to ``now_ns``,
        or release it back to wall time when ``now_ns`` is None.

        Both of the engine's clocks move together, including the one that stamps
        applied logs — so a balance change made while pinned is recorded at that
        instant, which is what makes a time-weighted average reproducible.

        While pinned, nothing the engine measures against this clock advances:
        lock and approval expiry, queue delays, price staleness, retry cadences.
        Release it before any scenario that depends on those.
        """
        return cast(dict[str, Any], await self._post("admin/clock", json_data={"now_ns": now_ns}))

    async def get_clock(self) -> dict[str, Any]:
        """Admin-only API: what the clearing engine's clock reads, and whether it is pinned."""
        return cast(dict[str, Any], await self._get("admin/clock"))

    async def set_interest_schedule(self, enabled: bool) -> dict:
        """Turn the clearing engine's periodic interest rate request on or off (debug only).

        On-demand triggers and rates injected directly still apply. Every rate
        application reseeds each user's average spot balance, so a scenario asserting
        an average has to be the only thing applying rates.
        """
        return await self._post("admin/interest/schedule", json_data={"enabled": enabled})

    async def get_user_inventory(self, user: "UserPublicKey", now_ns: int | None = None):
        """
        Admin-only API for checking a user inventory.

        Carries ``average_spot_deposits`` beside ``accounts``: per sub-account
        index, each tracked asset's time-weighted average spot balance and the
        balance it converges to. ``now_ns`` reads those averages at that instant
        instead of the clearing engine's clock, so a window can be read as it
        will stand later without waiting; the instant used comes back as
        ``computed_at_ns``.

        An average only reaches forward from the last balance change, so an
        instant before one is answered with ``INVALID_REQUEST`` naming where that
        asset's window starts — never with a zero, which is a real average.
        """
        if not isinstance(user, UserPublicKey):
            user = UserPublicKey.__validate_user__(user)

        params = {} if now_ns is None else {"now_ns": now_ns}
        return await self._get(f"admin/inventory/{user}", params=params)

    async def get_representation_rate(self, token: str) -> int | None:
        """
        Admin-only API for the rate a representation token converts at now, or None without one.
        """
        response = await self._get(f"admin/representation-rate/{token}")
        rate = response.get("rate")
        return None if rate is None else int(rate, 0)

    async def read_representation_rates(self):
        """
        Admin-only API asking every mapped provider for its rate now (debug builds). It returns
        once the reads are sent, so the new rates land after it.
        """
        await self._post("admin/representation-rates/read", json_data={})

    async def get_vault_balance(self, token: str) -> VaultBalance:
        """
        Admin-only API for a token's free and locked vault balance at 18 decimals.
        """
        response = await self._get(f"admin/vault/{token}")
        return VaultBalance.model_validate(response)

    async def set_asset_config(
        self,
        asset_id: int | AssetIdentifier | str,
        chain_id: str,
        max_deposits: str | int,
        address: str,
        max_1hr_deposits: str | int,
        min_weight: str | int,
    ):
        asset_index = _asset_id_to_index(asset_id)
        config = {
            "address": address,
            "max_deposits": to_u256_str(max_deposits),
            "max_1hr_deposits": to_u256_str(max_1hr_deposits),
            "min_weight": to_u256_str(min_weight),
        }

        await self._post(
            "admin/asset-config/modify",
            json_data={"asset_index": asset_index, "chain_id": chain_id, "config": config},
        )

    async def set_risk_parameters(
        self,
        asset_id: int | AssetIdentifier | str,
        collateral_factor: int,
        liability_factor: int,
        max_collateral: str,
        max_total_open_interest_notional: str,
        max_spot_open_interest: str,
        max_utilization: str,
        isolated_only: bool,
        initial_margin_clamps: list[int],
        initial_margin_factors: list[int],
        max_funding_rate: int,
        max_utilization_rate: int,
        utilization_kinks: list[int],
        rate_at_kinks: list[int],
        quote_utilization_kinks: list[int],
        quote_rate_at_kinks: list[int],
        skew_factor: int,
        base_funding_rate: int,
        skew_cliff: int,
        premium_clamp: int,
        buffer_multiplier: int,
        min_sub_account_balance: str | int = 0,
        max_adl: str | int = 0,
    ):
        asset_index = _asset_id_to_index(asset_id)
        risk_parameters = {
            "collateral_factor": collateral_factor,
            "liability_factor": liability_factor,
            "max_collateral": to_u256_str(max_collateral),
            "max_total_open_interest_notional": to_u256_str(max_total_open_interest_notional),
            "max_spot_open_interest": to_u256_str(max_spot_open_interest),
            "max_utilization": to_u256_str(max_utilization),
            "isolated_only": isolated_only,
            "initial_margin_clamps": initial_margin_clamps,
            "initial_margin_factors": initial_margin_factors,
            "max_funding_rate": max_funding_rate,
            "max_utilization_rate": max_utilization_rate,
            "utilization_kinks": utilization_kinks,
            "rate_at_kinks": rate_at_kinks,
            "quote_utilization_kinks": quote_utilization_kinks,
            "quote_rate_at_kinks": quote_rate_at_kinks,
            "skew_factor": skew_factor,
            "base_funding_rate": base_funding_rate,
            "skew_cliff": skew_cliff,
            "premium_clamp": premium_clamp,
            "buffer_multiplier": buffer_multiplier,
            "min_sub_account_balance": to_u256_str(min_sub_account_balance),
            # Zero disables auto-deleverage for the asset.
            "max_adl_usd": to_u256_str(max_adl),
        }
        await self._post(
            "admin/risk-parameters/modify",
            json_data={
                "asset_id": asset_index,
                "risk_parameters": risk_parameters,
            },
        )

    async def set_representation_rate_mapping(self, request: SetRepresentationRateMappingRequest):
        """Rotate the representation-rate mapping. A request with no mapping clears it."""
        await self._post(
            "representation-rate-mapping/set", json_data=request.model_dump(mode="json")
        )

    async def set_withdrawal_delay_params(
        self,
        min_delay: int,
        max_delay: int,
        delay_clamps: list[int],
        delay_values: list[int],
        cap_floor: int = 50_000,
    ):
        await self._post(
            "admin/withdrawal-delay-parameters/modify",
            json_data={
                "withdrawal_delay_parameters": {
                    "min_delay": min_delay,
                    "max_delay": max_delay,
                    "delay_clamps": delay_clamps,
                    "delay_values": delay_values,
                    "cap_floor": cap_floor,
                },
            },
        )

    async def set_oracle_prices(
        self, asset_id: AssetIdentifier, asset_price: str | None, asset_price_decimals: int
    ):
        prices: dict[str, Any]
        if asset_price:
            prices = {
                str(asset_id): {"price": to_u256_str(asset_price), "decimals": asset_price_decimals}
            }
        else:
            prices = {str(asset_id): None}

        await self._post("admin/oracle-prices/modify", json_data={"prices": prices})

    async def set_last_trade(
        self,
        asset_id: AssetIdentifier,
        asset_last_price: str | None,
        asset_last_price_decimals: int,
    ):
        prices: dict[str, Any]
        if asset_last_price:
            prices = {
                str(asset_id): {
                    "price": to_u256_str(asset_last_price),
                    "decimals": asset_last_price_decimals,
                }
            }
        else:
            prices = {str(asset_id): None}

        await self._post("admin/last-trade-prices/modify", json_data={"prices": prices})

    async def set_mark_price(
        self,
        asset_id: AssetIdentifier,
        asset_mark_price: str | None,
        asset_mark_price_decimals: int,
    ):
        """Force the mark price of an asset on the CE (debug only).

        Bypasses the last-trade EMA: the CE (and the OMS/MDS it propagates to)
        report exactly this mark until the next trade nudges it again. Pass
        ``asset_mark_price=None`` to clear the mark.
        """
        prices: dict[str, Any]
        if asset_mark_price:
            prices = {
                str(asset_id): {
                    "price": to_u256_str(asset_mark_price),
                    "decimals": asset_mark_price_decimals,
                }
            }
        else:
            prices = {str(asset_id): None}

        await self._post("admin/mark-prices/modify", json_data={"prices": prices})

    async def set_impact_prices(
        self,
        asset_id: AssetIdentifier,
        buy_impact: str | None,
        sell_impact: str | None,
        decimals: int = 0,
    ):
        """Override the buy/sell impact prices for an asset on the CE (debug only).

        The CE applies the override locally and propagates it to the OMS. Pass
        ``buy_impact=None`` and ``sell_impact=None`` (the default) to clear the
        override and set the asset's impact price back to ``None``.
        """
        prices: dict[str, Any]
        if buy_impact is None and sell_impact is None:
            prices = {str(asset_id): None}
        else:
            override: dict[str, Any] = {}
            if buy_impact is not None:
                override["buy_impact"] = {"price": to_u256_str(buy_impact), "decimals": decimals}

            if sell_impact is not None:
                override["sell_impact"] = {"price": to_u256_str(sell_impact), "decimals": decimals}

            prices = {str(asset_id): override}

        await self._post("admin/impact-prices/modify", json_data={"prices": prices})

    async def set_book_decimals(
        self,
        asset_id: int | AssetIdentifier | str,
        book_price_decimals: int,
        book_quantity_decimals: int,
    ):
        if not isinstance(asset_id, AssetIdentifier):
            asset_id = AssetIdentifier.model_validate(asset_id)

        asset_id = asset_id.model_dump()

        await self._post(
            "admin/book-decimals/modify",
            json_data={
                "asset_id": asset_id,
                "book_price_decimals": book_price_decimals,
                "book_quantity_decimals": book_quantity_decimals,
            },
        )

    async def set_trader_as_mm(
        self,
        user: "UserType",
        is_mm: bool,
        operator_secret: str,
        timestamp_ns: int | None = None,
        nonce: int | None = None,
    ):
        ts = time.time_ns() if timestamp_ns is None else timestamp_ns
        request_nonce = time.time_ns() if nonce is None else nonce

        sk = AdminClient._load_operator_sk(operator_secret=operator_secret)
        user_public_key = to_user_public_key(user)
        user_pubkey = bytes.fromhex(user_public_key)
        payload = (
            b"ce.admin.status.modify.v1"
            + request_nonce.to_bytes(8, "big")
            + ts.to_bytes(8, "big")
            + user_pubkey
            + (b"\x01" if is_mm else b"\x00")
        )
        sig = AdminClient._sign(payload, sk)

        await self._post(
            "admin/status/modify",
            json_data={
                "inner": {
                    "user": user_public_key,
                    "is_mm": is_mm,
                    "timestamp_ns": ts,
                    "nonce": request_nonce,
                },
                "signature": sig,
            },
        )

    async def set_interest_rates(self, rates: list[InterestRates]):
        await self._post(
            "admin/interest/inject",
            # Separate debug applications must not look like duplicate deliveries.
            json_data={
                "request_id": time.time_ns(),
                "rates": [r.model_dump(mode="json") for r in rates],
            },
        )

    async def request_interest_rates(self):
        """Fire the hourly CE -> interest engine rate request now (debug builds)."""
        await self._post("admin/interest/request", json_data={})

    async def get_average_open_interest(
        self, user: "UserPublicKey", after_last_update_ns: int | None = None
    ) -> list[dict[str, Any]]:
        """Per-market 14-day average and current notional OI (USD, 18 decimals).
        ``after_last_update_ns`` reads each average that long after the market's
        last position change instead of now."""
        if not isinstance(user, UserPublicKey):
            user = UserPublicKey.__validate_user__(user)
        params = (
            {} if after_last_update_ns is None else {"after_last_update_ns": after_last_update_ns}
        )
        windows = await self._get(f"admin/average-oi/{user}", params=params)
        return cast(list[dict[str, Any]], windows)

    async def set_average_open_interest(
        self, user: "UserPublicKey", asset: "AssetIdentifier", notional_usd: str
    ):
        """Seed a flat 14-day average notional OI (USD, 18 decimals) for a user and market."""
        if not isinstance(user, UserPublicKey):
            user = UserPublicKey.__validate_user__(user)
        if not isinstance(asset, AssetIdentifier):
            asset = AssetIdentifier.model_validate(asset)
        await self._post(
            "admin/average-oi/modify",
            json_data={"user": user, "asset": asset.model_dump(), "notional_usd": notional_usd},
        )

    async def set_fee_account(self, user: UserPublicKey):
        await self._post(
            "admin/fee-account/modify",
            json_data={"fee_account": user},
        )

    async def set_withdrawal_suspension(self, user: UserPublicKey, suspended: bool):
        """Debug-only: suspend or resume ``user``'s withdrawals directly."""
        await self._post(
            "admin/withdrawal-suspension/modify",
            json_data={"user": user, "suspended": suspended},
        )

    async def inject_withdrew(
        self,
        user: UserPublicKey,
        nonce: int,
        asset_address: str,
        amount: int,
        block_number: int | None = None,
    ) -> None:
        """Debug-only: propose a ``Withdrew`` event the vault never emitted, as if it had.

        ``amount`` is the chain amount, in the token's own decimals. The vault signs what it
        pays, so this is the only way to ingest a payout that differs from its approval.

        ``block_number`` dates the event. A vault balance read at or after it already counts
        the payout, so an event left at height zero never leaves the tracked vault balance
        once any read landed."""
        json_data: dict[str, Any] = {
            "user": user,
            "nonce": nonce,
            "asset_address": asset_address,
            "amount": str(amount),
        }
        if block_number is not None:
            json_data["block_number"] = block_number
        await self._post("admin/chain-event/withdrew", json_data=json_data)

    async def inject_settled(
        self,
        user: UserPublicKey,
        sub_account_index: int,
        nonce: int,
        token_out: str,
        amount_out: int,
        token_in: str,
        amount_in: int,
        mode: str,
        settler: UserPublicKey,
        block_number: int | None = None,
    ) -> None:
        """Debug-only: propose a ``Settled`` event the vault never emitted, as if it had.

        Amounts are chain amounts, in each token's own decimals; ``mode`` is ``spot`` or
        ``margin``.

        ``block_number`` dates the event. A vault balance read at or after it already counts
        the settlement's legs, so an event left at height zero never moves the tracked vault
        balance once any read landed."""
        json_data: dict[str, Any] = {
            "user": user,
            "sub_account_index": sub_account_index,
            "nonce": nonce,
            "token_out": token_out,
            "amount_out": str(amount_out),
            "token_in": token_in,
            "amount_in": str(amount_in),
            "mode": mode,
            "settler": settler,
        }
        if block_number is not None:
            json_data["block_number"] = block_number
        await self._post("admin/chain-event/settled", json_data=json_data)

    async def set_avs_backstop_target(self, user: UserPublicKey | None):
        """Configure the AVS backstop user, or clear it (disabling the
        post-liquidation transfer) when ``user`` is ``None``.

        Sub-accounts are allocated per transfer, so there is no index to set."""
        await self._post(
            "admin/avs-backstop-target/modify",
            json_data={"user": user},
        )

    async def clear_avs_backstop_target(self):
        await self.set_avs_backstop_target(None)

    async def reset_users(self):
        await self._post(
            "admin/users/reset",
            json_data={},
        )

    async def reset_max_one_hr_deposit(self):
        await self._post(
            "admin/deposits/reset-1hr",
            json_data={},
        )

    async def lock_xm_venue(
        self,
        user: UserPublicKey,
        venue: int,
        locked_at_ns: int,
        expiry_ns: int,
    ):
        """Lock one cross-venue link with an explicit creation time (debug only).

        A venue's netting offset decays toward nothing over the lock's age, so
        tests backdate ``locked_at_ns`` to observe a partly-decayed offset
        without waiting hours or days of real downtime.
        """
        await self._post(
            "admin/xm/lock-venue",
            json_data={
                "user": user,
                "venue": venue,
                "locked_at_ns": locked_at_ns,
                "expiry_ns": expiry_ns,
            },
        )

    async def expire_xm_venue_locks(self):
        """Force-expire every cross-venue (Hyperliquid) state-lock now (debug only).

        Simulates the inaccessible-/downtime-timeout cliff: each locked venue
        balance is zeroed and the (now smaller) credit line is gossiped to the
        OMS. Lets e2e tests observe the post-timeout solvency drop without
        waiting the real 7-day ``VENUE_INACCESSIBLE_TIMEOUT_NS``.
        """
        await self._post(
            "admin/xm/expire-locks",
            json_data={},
        )


def _asset_id_to_index(
    asset_id: int | AssetIdentifier | str,
) -> int:
    if isinstance(asset_id, AssetIdentifier):
        if asset_id.indexed:
            return int(asset_id.root)
        else:
            raise ValueError("unsupported")

    elif isinstance(asset_id, str):
        if asset_id.isnumeric():
            return int(asset_id)
        else:
            raise ValueError("unsupported")

    return int(asset_id)
