from typing import TYPE_CHECKING, Any

from tplus.client import ClearingEngineClient
from tplus.evm.contracts import DepositVault
from tplus.evm.managers.evm import ChainConnectedManager
from tplus.model.chain_address import ChainAddress
from tplus.model.types import ChainID, UserPublicKey
from tplus.utils.timeout import wait_for_condition
from tplus.utils.user import User

if TYPE_CHECKING:
    from tplus.evm.backends.base import EVMBackend


class VaultOwner(ChainConnectedManager):
    """
    This manager is for council use against the vault contract.
    It contains simpler operations for configuring vaults.
    """

    def __init__(
        self,
        owner: Any,
        vault: DepositVault | None = None,
        chain_id: ChainID | None = None,
        clearing_engine: "ClearingEngineClient | None" = None,
        *,
        backend: "EVMBackend | None" = None,
    ):
        self._set_backend(backend)
        self.owner = self.backend.get_account(owner)
        self.chain_id = chain_id or ChainID.evm(self.backend.chain_id)

        if vault is not None:
            self.vault = vault
        else:
            try:
                self.vault = DepositVault.latest_on_chain(backend=self.backend)
            except ValueError:
                self.vault = DepositVault(chain_id=self.chain_id, backend=self.backend)

        self.ce = clearing_engine

    async def register_settler(
        self,
        settler: UserPublicKey | User,
        executor: Any,
        wait: bool = False,
        **tx_kwargs,
    ) -> Any:
        """
        Allow a user to settler. Requires being the vault contract owner.
        """
        if isinstance(settler, User):
            settler = settler.public_key

        executor = self.backend.convert_address(executor)
        tx_kwargs.setdefault("sender", self.owner)
        tx = self.vault.add_settler_executor(settler, executor, **tx_kwargs)

        if wait:
            if not (ce := self.ce):
                raise ValueError("Must have clearing_engine to wait for settler registration.")

            vault_address = ChainAddress.from_evm_address(str(self.vault.address), self.chain_id)
            await wait_for_condition(
                update_fn=lambda: ce.admin_settlements.update_approved_settlers(vault_address),
                get_fn=lambda: ce.admin_settlements.get_approved_settlers(self.chain_id),
                check_fn=lambda by_vault: settler in by_vault.get(vault_address.address, []),
                timeout=10,
                interval=1,
                error_msg="Settler approval failed.",
            )

        return tx

    async def register_depositor(self, depositor: Any) -> Any:
        depositor = self.backend.convert_address(depositor)
        return self.vault.setDepositorStatus(depositor, True, sender=self.owner)
