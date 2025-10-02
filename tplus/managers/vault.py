import asyncio
import time
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

    async def register_admin(self, admin_key: str | None = None) -> "ReceiptAPI":
        """
        Register the connected clearing-engine as a valid deposit vault admin.
        Requires being the vault contract owner.
        """
        if admin_key is None:
            if self.ce is None:
                raise ValueError("Either admin_key or self.ce must be specified")

            admin_key = await self.ce.admin.get_verifying_key()

        address = public_key_to_address(admin_key)
        return self.vault.setAdmin(address, True, sender=self.owner_eoa)

    async def register_settler(
        self,
        settler: UserPublicKey,
        executor: "AddressType | str | AccountAPI | ContractInstance",
        wait: bool = False,
    ) -> "ReceiptAPI":
        """
        Allow a user to settler. Requires being the vault contract owner.
        """
        tx = self.vault.setSettlerExecutor(settler, executor, sender=self.owner_eoa)

        if wait:
            if not (ce := self.ce):
                raise ValueError("Must have clearing_engine to wait for settler registration.")

            # Wait for the settler to appear in the CE's list of approved settlers.
            found = False
            timeout = 10  # Seconds
            start = int(time.time())
            while int(time.time()) - start <= timeout:
                await self.ce.settlements.update_approved_settlers(self.chain_id, self.vault.address)
                settlers = await ce.settlements.get_approved_settlers(self.chain_id)
                if settler in settlers:
                    found = True
                    break

                await asyncio.sleep(1)

            if not found:
                raise Exception("Settler approval failed.")

        return tx
