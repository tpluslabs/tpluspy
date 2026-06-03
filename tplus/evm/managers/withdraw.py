import asyncio
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hexbytes import HexBytes

from tplus.client.clearingengine import ClearingEngineClient
from tplus.client.withdrawal import WithdrawalClient
from tplus.evm.contracts import DepositVault
from tplus.evm.managers.evm import ChainConnectedManager
from tplus.exceptions import OmsError
from tplus.logger import get_logger
from tplus.model.asset_identifier import Address32, AssetAddress, AssetIdentifier
from tplus.model.types import ChainID
from tplus.model.withdrawal import WithdrawalRequest
from tplus.utils.address import to_evm_address

if TYPE_CHECKING:
    from ape.api.accounts import AccountAPI
    from ape.api.transactions import ReceiptAPI
    from ape.types.address import AddressType

    from tplus.utils.user import User


@dataclass
class WithdrawalInfo:
    """Information about a withdrawal tracked through init + execute."""

    asset: AssetAddress
    amount: int
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
        self.chain_id = chain_id or ChainID.evm(self.chain_manager.chain_id)
        self.vault = vault or DepositVault(chain_id=self.chain_id)
        self.logger = get_logger()

    async def init_withdrawal(
        self,
        asset: AssetAddress,
        amount: int,
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
        """
        user = user or self.default_user

        if nonce is None:
            nonce = self.vault.get_withdrawal_count(user)

        if target is None:
            target = Address32(self.ape_account.address)

        request = WithdrawalRequest.create_signed(
            signer=user,
            asset=asset,
            amount=amount,
            nonce=nonce,
            target=target,
        )

        await self.withdrawals.init_withdrawal(request)
        self.logger.info(
            f"Initialized withdrawal - Asset: {request.inner.asset}, "
            f"Amount: {amount}, Nonce: {nonce}"
        )

        info = WithdrawalInfo(
            asset=request.inner.asset,
            amount=amount,
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
            "amount": info.amount,
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
