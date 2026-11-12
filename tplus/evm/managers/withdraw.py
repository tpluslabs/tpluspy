import asyncio
import json
import os
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
from hexbytes import HexBytes
from websockets.exceptions import ConnectionClosed

from tplus.client.clearingengine import ClearingEngineClient
from tplus.client.oms.assetregistry import AssetRegistryClient
from tplus.client.withdrawal import WithdrawalClient
from tplus.evm.contracts import DepositVault
from tplus.evm.managers.evm import ChainSigningManager
from tplus.exceptions import OmsError
from tplus.logger import get_logger
from tplus.model.approval import WithdrawalApproval
from tplus.model.asset_identifier import Address32, AssetAddress, AssetIdentifier
from tplus.model.types import ChainID
from tplus.model.user_event import WithdrawalSignatureAvailable, parse_user_event
from tplus.model.withdrawal import WithdrawalRequest
from tplus.utils.address import to_evm_address
from tplus.utils.amount import Amount
from tplus.utils.user import to_user

if TYPE_CHECKING:
    from tplus.client.base import BaseClient
    from tplus.evm.backends.base import AccountLike, EVMBackend
    from tplus.types import UserLike

EVM_ROUTING_ID = 0

# Decimals for tokens that will never re-deploy with a different value, seeded into each
# manager's cache to skip the registry round-trip. Chain ID -> token address -> decimals.
KNOWN_DECIMALS: dict[int, dict[str, int]] = {
    1: {
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": 6,  # USDC
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": 18,  # WETH
    },
    42161: {
        "0xaf88d065e77c8cc2239327c5edb3a432268e5831": 6,  # USDC
        "0x82af49447d8a07e3bd95bd0d56f35241523fbab1": 18,  # WETH
    },
}


def build_seeded_decimals_cache() -> dict[str, int]:
    """``KNOWN_DECIMALS`` keyed the way :meth:`WithdrawalManager.get_asset_decimals` looks up."""
    return {
        str(AssetAddress.from_evm_address(address, chain_id)): decimals
        for chain_id, tokens in KNOWN_DECIMALS.items()
        for address, decimals in tokens.items()
    }


SEEDED_DECIMALS_CACHE = build_seeded_decimals_cache()


@dataclass
class WithdrawalInfo:
    """Information about a withdrawal tracked through init + execute."""

    asset: AssetAddress
    amount: int
    """The requested amount, in CE-internal 1e18 units."""

    nonce: int
    target: Address32
    chain_id: ChainID


class WithdrawalManager(ChainSigningManager):
    """
    Integrates the clearing-engine client with the vault contract to abstract
    away the full withdrawal lifecycle.
    """

    def __init__(
        self,
        default_user: "UserLike",
        account: "AccountLike | None" = None,
        clearing_engine: ClearingEngineClient | None = None,
        withdrawal_client: WithdrawalClient | None = None,
        chain_id: ChainID | None = None,
        vault: DepositVault | None = None,
        registry_client: AssetRegistryClient | None = None,
        *,
        backend: "EVMBackend | None" = None,
    ):
        super().__init__(default_user, account, backend)
        self.ce: ClearingEngineClient = clearing_engine or ClearingEngineClient(
            "http://127.0.0.1:3032", default_user=self.default_user
        )
        if withdrawal_client is not None:
            self.withdrawals = withdrawal_client
        else:
            oms_base_url = os.getenv("API_BASE_URL", "https://127.0.0.1:8000")
            oms_insecure_ssl = getattr(self.ce._settings, "insecure_ssl", False)
            self.withdrawals = WithdrawalClient(
                default_user=self.default_user,
                base_url=oms_base_url,
                insecure_ssl=oms_insecure_ssl,
            )
        self.registry_client = registry_client or AssetRegistryClient.from_client(self.withdrawals)
        self.chain_id = chain_id or ChainID.evm(self.backend.chain_id)
        self.vault = vault or DepositVault(chain_id=self.chain_id, backend=self.backend)
        self.logger = get_logger()
        self._decimals_cache: dict[str, int] = dict(SEEDED_DECIMALS_CACHE)

    def _user_clients(self) -> Iterable["BaseClient"]:
        # OMS first: it is the signer registry the T+ frontend resolves accounts against.
        return (self.withdrawals, self.ce, self.registry_client)

    async def get_asset_decimals(self, asset: AssetAddress) -> int:
        """
        The asset's native chain decimals, read from the registry snapshot the CE
        publishes. This is the same source the CE uses when signing withdrawal approvals.

        Falls back to the token's own ``decimals()`` when the registry is unreachable or
        holds no entry for the asset.
        """
        key = str(asset)
        if key in self._decimals_cache:
            return self._decimals_cache[key]

        try:
            decimals = (await self.registry_client.get_asset_decimals([asset])).get(key)
        except httpx.HTTPError as err:
            self.logger.warning(f"Registry decimals lookup failed for '{key}': {err}")
            decimals = None

        if decimals is None:
            decimals = self.get_erc20_decimals(asset)

        self._decimals_cache[key] = int(decimals)
        return self._decimals_cache[key]

    def get_erc20_decimals(self, asset: AssetAddress) -> int:
        """Read ``decimals()`` off the token contract itself."""
        if asset.chain_id.routing_id != EVM_ROUTING_ID:
            raise ValueError(f"Cannot read decimals on-chain for non-EVM asset '{asset}'.")

        return self.backend.get_erc20(asset.evm_address).call("decimals")

    async def init_withdrawal(
        self,
        asset: AssetAddress,
        amount: int | Amount,
        target: Address32 | str | None = None,
        user: "UserLike | None" = None,
        nonce: int | None = None,
        then_execute: bool = False,
        poll_interval: float = 2.0,
        poll_timeout: float = 60.0,
        max_fee: int | None = None,
    ) -> WithdrawalInfo:
        """
        Submit a withdrawal to the clearing engine.

        If ``then_execute`` is True, subscribe to signature hints and
        read status before submitting the on-chain ``withdraw`` transaction.

        Args:
            asset: The asset to withdraw.
            amount: An ``int`` is a CE-internal 1e18-normalized amount. An
                :class:`~tplus.utils.amount.Amount` is a native-decimals amount and is
                normalized here instead.
            max_fee: The most the withdrawal may reserve for its rebalancing fee, in
                CE-internal 1e18 units of the asset. The CE refuses a request quoted above
                it and fails the withdrawal if its approval prices above it; ``None``
                accepts whatever the protocol reserves.
        """
        user = to_user(user) if user is not None else await self.resolve_default_user()

        if nonce is None:
            nonce = self.vault.get_withdrawal_count(user)

        if target is None:
            target = Address32(self.account.address)

        if isinstance(amount, Amount):
            request_amount = amount.to_inventory_amount("down")
        else:
            request_amount = amount

        request = WithdrawalRequest.create_signed(
            signer=user,
            asset=asset,
            amount=request_amount,
            nonce=nonce,
            target=target,
            max_fee=max_fee,
        )

        info = WithdrawalInfo(
            asset=request.inner.asset,
            amount=request_amount,
            nonce=nonce,
            target=request.inner.target,
            chain_id=self.chain_id,
        )
        if not then_execute:
            await self.withdrawals.init_withdrawal(request)
            return info

        # Wait for the server to acknowledge the subscription before submitting init.
        ready = asyncio.get_running_loop().create_future()
        changed = asyncio.Event()
        watcher = asyncio.create_task(
            self._watch_signature_hints(user, nonce, ready, changed, poll_interval)
        )
        submitted = False
        try:
            await asyncio.wait_for(ready, poll_timeout)
            submitted = True
            await self.withdrawals.init_withdrawal(request)
            changed.set()  # Initial status also covers an approval already present at subscription.
            approvals = await asyncio.wait_for(
                self._wait_for_approvals(user.public_key, nonce, changed, poll_interval),
                poll_timeout,
            )
            await self.execute_withdrawal(info, approvals, user=user)
        except asyncio.TimeoutError as err:
            if not submitted:
                raise TimeoutError(
                    "Withdrawal event stream unavailable; nothing was submitted."
                ) from err
            raise TimeoutError(
                f"Withdrawal outcome unknown (chain={self.chain_id}, nonce={nonce}); "
                "check withdrawal status before retrying."
            ) from err
        finally:
            watcher.cancel()
            with suppress(asyncio.CancelledError):
                await watcher
        return info

    async def _watch_signature_hints(self, user, nonce, ready, changed, reconnect_delay):
        while True:
            try:
                connection = await self.withdrawals.open_ws(
                    f"/account/events/{user.public_key}", user=user
                )
                async with connection as websocket:
                    subscribed = False
                    async for message in websocket:
                        try:
                            payload = json.loads(message)
                            if isinstance(payload, dict) and payload.get("type") == "subscriptions":
                                if payload.get("errors") or not payload.get("channels"):
                                    continue
                                subscribed = True
                                if not ready.done():
                                    ready.set_result(None)
                                changed.set()  # Resynchronize after every acknowledged connection.
                                continue
                            if not subscribed:
                                continue
                            event = parse_user_event(payload)
                        except (ValueError, TypeError):
                            continue
                        if (
                            isinstance(event, WithdrawalSignatureAvailable)
                            and event.user == user.public_key
                            and event.chain_id == str(self.chain_id)
                            and event.withdrawal_nonce == nonce
                        ):
                            changed.set()
            except (ConnectionClosed, OSError, httpx.HTTPError) as err:
                self.logger.warning(f"Withdrawal event stream disconnected: {err}")
            except Exception as err:
                if not ready.done():
                    ready.set_exception(err)
                raise
            await asyncio.sleep(reconnect_delay)

    async def _wait_for_approvals(
        self,
        user_pubkey: str,
        nonce: int,
        changed: asyncio.Event,
        reconnect_delay: float = 2.0,
    ) -> list[WithdrawalApproval]:
        while True:
            await changed.wait()
            changed.clear()
            try:
                rows = await self.withdrawals.get_withdrawal_status(user_pubkey)
            except OmsError as err:
                if err.code == "TIMEOUT_UNKNOWN_STATE":
                    # Retry this failed read: the triggering hint need not be repeated.
                    # The caller's overall timeout bounds retries; an empty successful
                    # read still waits for the next hint or reconnect.
                    await asyncio.sleep(reconnect_delay)
                    changed.set()
                    continue
                raise
            for row in rows:
                if row.get("nonce") != nonce:
                    continue
                status = row.get("status", {})
                if status.get("type") != "approved":
                    continue
                payloads = status.get("approvals", [])
                if not payloads or any(a.get("chain_id") != str(self.chain_id) for a in payloads):
                    continue
                approvals = [WithdrawalApproval.model_validate(a) for a in payloads]
                if approvals and all(a.inner.nonce == nonce for a in approvals):
                    # The status route separates different signed payloads into different rows.
                    first = approvals[0]
                    if all(
                        (a.amount, a.expiry, a.epoch_hash)
                        == (first.amount, first.expiry, first.epoch_hash)
                        for a in approvals
                    ):
                        return approvals

    async def execute_withdrawal(
        self,
        info: WithdrawalInfo,
        approvals: list[WithdrawalApproval],
        user: "UserLike | None" = None,
        target: str | None = None,
        **kwargs,
    ) -> Any:
        """Execute an approved withdrawal on-chain.

        The vault call uses the chain amount the approvals signed, not the 1e18-normalized
        ``info.amount`` the CE request carried.

        Args:
            info: The :class:`WithdrawalInfo` returned by :meth:`init_withdrawal`.
            approvals: All withdrawal approvals whose inner nonce
                matches the withdrawal. Each contributes one admin signature
                toward the contract-enforced withdrawal quorum.
        """
        if not approvals:
            raise ValueError("At least one approval is required.")

        user = to_user(user) if user is not None else await self.resolve_default_user()
        kwargs.setdefault("sender", self.account)
        kwargs.setdefault("required_confirmations", 0)

        first = approvals[0]
        resolved_target = target
        if resolved_target is None:
            resolved_target = to_evm_address(f"0x{str(info.target)[:40]}")

        asset_address = (
            info.asset.evm_address
            if isinstance(info.asset, AssetIdentifier | AssetAddress)
            else info.asset
        )

        withdrawal = {
            "tokenAddress": asset_address,
            "amount": first.amount,
            "nonce": info.nonce,
        }

        signatures = [approval.inner.signature for approval in approvals]

        return self.vault.withdraw(
            withdrawal,
            HexBytes(user.public_key),
            resolved_target,
            first.expiry,
            first.epoch_hash,
            signatures,
            **kwargs,
        )
