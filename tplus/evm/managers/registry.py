from typing import TYPE_CHECKING

from tplus.evm.contracts import Registry
from tplus.evm.managers.evm import ChainConnectedManager
from tplus.utils.timeout import wait_for_condition

if TYPE_CHECKING:
    from ape.api.accounts import AccountAPI
    from ape.types.address import AddressType

    from tplus.client.clearingengine import ClearingEngineClient


class RegistryOwner(ChainConnectedManager):
    """
    For registry (`Registry.sol`) operations using the owner of the contract.
    """

    def __init__(
        self,
        owner: "AccountAPI",
        registry: Registry | None = None,
        chain_id: int | None = None,
        clearing_engine: "ClearingEngineClient | None" = None,
    ):
        self.owner = owner
        self.chain_id = chain_id or self.chain_manager.chain_id

        if registry is None:
            self.registry = Registry(chain_id=self.chain_id)
        else:
            self.registry = registry

        self.ce = clearing_engine

    async def add_vault(self, vault: "AddressType", wait: bool = False, **tx_kwargs):
        """
        Add a vault to the registry.

        Args:
            vault (AddressType): The vault to add.
            wait (bool): If true and the CE exists, will wait for the vault to be registered in the CE.
            tx_kwargs: Additional tx kwargs.

        Returns:
            ReceiptAPI
        """
        tx_kwargs.setdefault("sender", self.owner)
        tx = self.registry.addVault(self.chain_manager.chain_id, vault, **tx_kwargs)

        if wait:
            if not (ce := self.ce):
                raise ValueError("Must have clearing_engine to wait for vault registration.")

            await wait_for_condition(
                update_fn=lambda: ce.vaults.update(),
                get_fn=lambda: ce.vaults.get(),
                # cond: checks if the vault EVM address is part any of the ChainAddress returned.
                check_fn=lambda vaults: any(vault in vault_ca for vault_ca in vaults),
                timeout=10,
                interval=1,
                error_msg="Vault registration failed.",
            )

        return tx
