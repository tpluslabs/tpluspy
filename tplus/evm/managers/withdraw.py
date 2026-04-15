import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hexbytes import HexBytes

from tplus.client.clearingengine import ClearingEngineClient
from tplus.evm.contracts import DepositVault
from tplus.evm.managers.evm import ChainConnectedManager
from tplus.logger import get_logger
from tplus.model.asset_identifier import Address32, AssetAddress, AssetIdentifier
from tplus.model.types import ChainID
from tplus.model.withdrawal import WithdrawalRequest

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
        chain_id: ChainID | None = None,
        vault: DepositVault | None = None,
    ):
        self.default_user = default_user
        self.ape_account = ape_account
        self.ce: ClearingEngineClient = clearing_engine or ClearingEngineClient(
            self.default_user, "http://127.0.0.1:3032"
        )
        self.chain_id = chain_id or ChainID.evm(self.chain_manager.chain_id)
        self.vault = vault or DepositVault(chain_id=self.chain_id)
        self.logger = get_logger()

    async def init_withdrawal(
        self,
        asset: AssetAddress | str,
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
            nonce = self.vault.get_withdrawal_count(user, user.sub_account)

        request = WithdrawalRequest.create_signed(
            signer=user,
            asset=asset,
            amount=amount,
            chain_id=self.chain_id,
            nonce=nonce,
            target=target,
        )

        await self.ce.withdrawals.init_withdrawal(request)
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
            signatures = await self.ce.withdrawals.get_signatures(user_pubkey)
            matching = [s for s in signatures if s.get("inner", {}).get("nonce") == nonce]
            if matching:
                return matching
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
            # Zero Address32 means "no explicit target" — fall back to the signer.
            if int(info.target, 16) == 0:
                resolved_target = self.ape_account.address
            else:
                resolved_target = info.target.evm_address

        asset_address = (
            info.asset.evm_address if isinstance(info.asset, AssetIdentifier) else info.asset
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
