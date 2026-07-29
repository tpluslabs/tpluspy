import asyncio
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
from hexbytes import HexBytes

from tplus.client.clearingengine import ClearingEngineClient
from tplus.client.oms.assetregistry import AssetRegistryClient
from tplus.client.withdrawal import WithdrawalClient
from tplus.evm.abi import get_erc20_type
from tplus.evm.contracts import DepositVault
from tplus.evm.managers.evm import ChainConnectedManager
from tplus.exceptions import OmsError
from tplus.logger import get_logger
from tplus.model.asset_identifier import Address32, AssetAddress, AssetIdentifier
from tplus.model.types import ChainID
from tplus.model.withdrawal import WithdrawalRequest
from tplus.utils.address import to_evm_address
from tplus.utils.amount import Amount
from tplus.utils.decimals import to_chain_decimals

if TYPE_CHECKING:
    from ape.api.accounts import AccountAPI
    from ape.api.transactions import ReceiptAPI
    from ape.types.address import AddressType

    from tplus.utils.user import User

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

    chain_amount: int
    """
    ``amount`` converted to the asset's native chain decimals. This is the amount the CE
    covered with its approval signature, so it is the only one the vault digest matches.
    """

    nonce: int
    target: Address32
    chain_id: ChainID


class WithdrawalManager(ChainConnectedManager):
    """
    Integrates the clearing-engine client with the vault contract via Ape to
    abstract away the full withdrawal lifecycle.
    """

    def __init__(
        self,
        default_user: "User",
        ape_account: "AccountAPI",
        clearing_engine: ClearingEngineClient | None = None,
        withdrawal_client: WithdrawalClient | None = None,
        chain_id: ChainID | None = None,
        vault: DepositVault | None = None,
        registry_client: AssetRegistryClient | None = None,
    ):
        self.default_user = default_user
        self.ape_account = ape_account
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
        self.chain_id = chain_id or ChainID.evm(self.chain_manager.chain_id)
        self.vault = vault or DepositVault(chain_id=self.chain_id)
        self.logger = get_logger()
        self._decimals_cache: dict[str, int] = dict(SEEDED_DECIMALS_CACHE)

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

        token = self.chain_manager.contracts.instance_at(
            asset.evm_address, contract_type=get_erc20_type()
        )
        return token.decimals()

    async def init_withdrawal(
        self,
        asset: AssetAddress,
        amount: int | Amount,
        target: Address32 | str | None = None,
        user: "User | None" = None,
        nonce: int | None = None,
        then_execute: bool = False,
        poll_interval: float = 2.0,
        poll_timeout: float = 60.0,
    ) -> WithdrawalInfo:
        """
        Submit a withdrawal to the clearing engine.

        If ``then_execute`` is True, poll the CE for an approval signature and
        submit the on-chain ``withdraw`` transaction once it arrives.

        Args:
            asset: The asset to withdraw.
            amount: An ``int`` is a CE-internal 1e18-normalized amount and the asset's
                decimals are looked up from the registry. An :class:`~tplus.utils.amount.Amount`
                is a native-decimals amount and is normalized here instead.
        """
        user = user or self.default_user

        if nonce is None:
            nonce = self.vault.get_withdrawal_count(user)

        if target is None:
            target = Address32(self.ape_account.address)

        if isinstance(amount, Amount):
            decimals: int | None = amount.decimals
            request_amount = amount.to_inventory_amount("down")
        else:
            decimals = None
            request_amount = amount

        request = WithdrawalRequest.create_signed(
            signer=user,
            asset=asset,
            amount=request_amount,
            nonce=nonce,
            target=target,
        )

        if decimals is None:
            decimals = await self.get_asset_decimals(request.inner.asset)

        # The CE signs the chain-decimals amount, rounding down; the vault digest only
        # matches if the on-chain call uses that exact value.
        chain_amount = to_chain_decimals(request_amount, decimals, "down")

        await self.withdrawals.init_withdrawal(request)
        self.logger.info(
            f"Initialized withdrawal - Asset: {request.inner.asset}, "
            f"Amount: {request_amount}, Chain amount: {chain_amount}, Nonce: {nonce}"
        )

        info = WithdrawalInfo(
            asset=request.inner.asset,
            amount=request_amount,
            chain_amount=chain_amount,
            nonce=nonce,
            target=request.inner.target,
            chain_id=self.chain_id,
        )

        if then_execute:
            approvals = await self._wait_for_approvals(
                user.public_key, nonce, poll_interval, poll_timeout
            )
            await self.execute_withdrawal(info, approvals, user=user)

        return info

    async def _wait_for_approvals(
        self, user_pubkey: str, nonce: int, interval: float, timeout: float
    ) -> list[dict[str, Any]]:
        """Poll the CE until at least one approval arrives for ``nonce``.

        Returns every approval whose inner nonce matches; the caller passes the
        full list on-chain to satisfy the withdrawal quorum.
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout

        while loop.time() < deadline:
            try:
                queued = await self.withdrawals.get_queued_withdrawals(user_pubkey)
            except OmsError as err:
                # Queue polling is read-only; transient CE overlay timeouts should
                # not fail approval polling.
                if err.code == "TIMEOUT_UNKNOWN_STATE":
                    await asyncio.sleep(interval)
                    continue
                raise
            for withdrawal in queued:
                if withdrawal.get("nonce") != nonce:
                    continue
                status = withdrawal.get("status")
                if not isinstance(status, dict):
                    continue
                if status.get("type") != "approved":
                    continue
                approvals = status.get("approvals")
                if isinstance(approvals, list) and approvals:
                    return approvals
            await asyncio.sleep(interval)

        raise TimeoutError(f"Timed out waiting for withdrawal approval (nonce={nonce}).")

    async def execute_withdrawal(
        self,
        info: WithdrawalInfo,
        approvals: list[dict[str, Any]],
        user: "User | None" = None,
        target: "AddressType | str | None" = None,
        **kwargs,
    ) -> "ReceiptAPI":
        """Execute an approved withdrawal on-chain.

        The vault call uses ``info.chain_amount`` (native token decimals), not the
        1e18-normalized ``info.amount`` the CE request carried.

        Args:
            info: The :class:`WithdrawalInfo` returned by :meth:`init_withdrawal`.
            approvals: All :class:`OneTimeSignature` dicts whose inner nonce
                matches the withdrawal. Each contributes one admin signature
                toward the contract-enforced withdrawal quorum.
        """
        if not approvals:
            raise ValueError("At least one approval is required.")

        user = user or self.default_user
        kwargs.setdefault("sender", self.ape_account)
        kwargs.setdefault("required_confirmations", 0)

        first = approvals[0]
        expiry = first["expiry"]
        epoch_hash = first.get("epoch_hash")
        if epoch_hash is None:
            raise ValueError("Withdrawal approval is missing epoch_hash.")

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
            "amount": info.chain_amount,
            "nonce": info.nonce,
        }

        signatures = [HexBytes(a["inner"]["signature"]) for a in approvals]

        return self.vault.withdraw(
            withdrawal,
            HexBytes(user.public_key),
            resolved_target,
            expiry,
            HexBytes(bytes(epoch_hash)),
            signatures,
            **kwargs,
        )
