from ape.utils.basemodel import ManagerAccessMixin
from typing import TYPE_CHECKING
from tplus.evm.contracts import Registry
from tplus.utils.timeout import wait_for_condition

if TYPE_CHECKING:
    from ape.types.address import AddressType
    from tplus.client.clearingengine import ClearingEngineClient


class RegistryOwner(ManagerAccessMixin):
    """
    For registry (`Registry.sol`) operations using the owner of the contract.
    """

    def __init__(
        self,
        owner_eoa: "AccountAPI",
        registry: Registry | None = None,
        chain_id: int | None = None,
        clearing_engine: "ClearingEngineClient | None" = None,
    ):
        self.owner_eoa = owner_eoa

        if registry is None:
            if chain_id is None:
                raise ValueError("Either vault or chain_id must be specified")

            self.registry = Registry(chain_id=chain_id)

        else:
            self.registry = registry

        self.chain_id = chain_id
        self.ce = clearing_engine

    async def add_vault(self, vault: "AddressType", wait: bool):
        """
        Add a vault to the registry.

        Args:
            vault (AddressType): The vault to add.
            wait (bool): If true and the CE exists, will wait for the vault to be registered in the CE.

        Returns:
            ReceiptAPI
        """
        tx = self.registry.addVault(self.chain_manager.chain_id, vault, sender=self.owner_eoa)

        if wait:
            if not (ce := self.ce):
                raise ValueError("Must have clearing_engine to wait for vault registration.")

            await wait_for_condition(
                update_fn=lambda: ce.settlements.update_approved_settlers(self.chain_id, self.vault.address),
                get_fn=lambda: ce.settlements.get_approved_settlers(self.chain_id),
                check_fn=lambda vaults: vault in vaults,
                timeout=10,
                interval=1,
                error_msg="Vault registration failed.",
            )

        return tx
