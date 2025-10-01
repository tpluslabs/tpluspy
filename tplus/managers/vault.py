from typing import TYPE_CHECKING

from ape.utils.basemodel import ManagerAccessMixin

from tplus.client import ClearingEngineClient
from tplus.evm.contracts import DepositVault
from tplus.model.types import UserPublicKey
from tplus.utils.address import public_key_to_address

if TYPE_CHECKING:
    from ape.api.accounts import AccountAPI
    from ape.api.transactions import ReceiptAPI
    from ape.contracts.base import ContractInstance
    from ape.types.address import AddressType


class VaultOwner(ManagerAccessMixin):
    """
    This manager is for council use against the vault contract.
    It contains simpler operations for configuring vaults.
    """

    def __init__(
        self,
        owner_eoa: "AccountAPI",
        vault: DepositVault | None = None,
        chain_id: int | None = None,
        clearing_engine: "ClearingEngineClient | None" = None,
    ):
        self.owner_eoa = owner_eoa

        if vault is None:
            if chain_id is None:
                raise ValueError("Either vault or chain_id must be specified")

            self.vault = DepositVault(chain_id=chain_id)

        else:
            self.vault = vault

        self.chain_id = chain_id
        self.ce = clearing_engine

    async def register_admin(self, *, vault_owner: "AccountAPI") -> "ReceiptAPI":
        """
        Register the connected clearing-engine as a valid deposit vault admin.
        Requires being the vault contract owner.
        """
        key = await self.ce.admin.get_verifying_key()
        address = public_key_to_address(key)
        return self.vault.setAdmin(address, True, sender=vault_owner)

    async def register_settler(
        self,
        settler: UserPublicKey,
        executor: "AddressType | str | AccountAPI | ContractInstance",
    ) -> "ReceiptAPI":
        """
        Allow a user to settler. Requires being the vault contract owner.
        """
        tx = self.vault.setSettlerExecutor(settler, executor, sender=self.owner_eoa)

        if self.ce is not None:
            await self.ce.settlements.update_approved_settlers(self.chain_id, self.vault.address)

        return tx
