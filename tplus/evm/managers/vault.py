from typing import TYPE_CHECKING

from tplus.client import ClearingEngineClient
from tplus.evm.address import public_key_to_address
from tplus.evm.contracts import DepositVault
from tplus.evm.eip712 import Domain
from tplus.evm.managers.evm import ChainConnectedManager
from tplus.model.types import UserPublicKey
from tplus.utils.timeout import wait_for_condition

if TYPE_CHECKING:
    from ape.api.accounts import AccountAPI
    from ape.api.transactions import ReceiptAPI
    from ape.contracts.base import ContractInstance
    from ape.types.address import AddressType


class VaultOwner(ChainConnectedManager):
    """
    This manager is for council use against the vault contract.
    It contains simpler operations for configuring vaults.
    """

    def __init__(
        self,
        owner: "AccountAPI",
        vault: DepositVault | None = None,
        chain_id: int | None = None,
        clearing_engine: "ClearingEngineClient | None" = None,
    ):
        self.owner = owner
        self.chain_id = chain_id or self.chain_manager.chain_id
        self.vault = vault or DepositVault(chain_id=self.chain_id)
        self.ce = clearing_engine

    def set_domain_separator(self, domain_separator: bytes, **tx_kwargs) -> "ReceiptAPI":
        tx_kwargs.setdefault("sender", self.owner)

        domain_separator = (
            domain_separator
            or Domain(
                _chainId_=self.chain_manager.chain_id,  # type: ignore
                _verifyingContract_=self.vault.address,  # type: ignore
            )._domain_separator_
        )

        return self.vault.set_domain_separator(domain_separator, **tx_kwargs)

    async def register_admin(
        self,
        admin_key: str | None = None,
        verify: bool = False,
        **tx_kwargs,
    ) -> "ReceiptAPI":
        """
        Register the connected clearing-engine as a valid deposit vault admin.
        Requires being the vault contract owner.
        """
        tx_kwargs.setdefault("sender", self.owner)

        if admin_key is None:
            if self.ce is None:
                raise ValueError("Either admin_key or self.ce must be specified")

            admin_key = await self.ce.admin.get_verifying_key()

        address = public_key_to_address(admin_key)

        tx = self.vault.setAdmin(address, True, **tx_kwargs)
        if verify:
            self.vault.isAdmin(address)

        return tx

    async def register_settler(
        self,
        settler: UserPublicKey,
        executor: "AddressType | str | AccountAPI | ContractInstance",
        wait: bool = False,
        **tx_kwargs,
    ) -> "ReceiptAPI":
        """
        Allow a user to settler. Requires being the vault contract owner.
        """
        tx_kwargs.setdefault("sender", self.owner)
        tx = self.vault.setSettlerExecutor(settler, executor, **tx_kwargs)

        if wait:
            if not (ce := self.ce):
                raise ValueError("Must have clearing_engine to wait for settler registration.")

            await wait_for_condition(
                update_fn=lambda: ce.settlements.update_approved_settlers(
                    self.chain_id, self.vault
                ),
                get_fn=lambda: ce.settlements.get_approved_settlers(self.chain_id),
                check_fn=lambda settlers: settler in settlers,
                timeout=10,
                interval=1,
                error_msg="Settler approval failed.",
            )

        return tx
