from typing import TYPE_CHECKING, Any

from tplus.client import ClearingEngineClient
from tplus.evm.address import public_key_to_address
from tplus.evm.contracts import DepositVault
from tplus.evm.managers.evm import ChainConnectedManager
from tplus.model.types import ChainID, UserPublicKey
from tplus.utils.address import to_evm_address
from tplus.utils.domain import get_dstack_domain
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

    def set_domain_separator(self, domain_separator: bytes | None = None, **tx_kwargs) -> Any:
        tx_kwargs.setdefault("sender", self.owner)

        domain_separator = domain_separator or get_dstack_domain(self.vault.chain_address)

        return self.vault.set_domain_separator(domain_separator, **tx_kwargs)

    def set_credential_manager(self, new_credential_manager: Any, **tx_kwargs) -> Any:
        tx_kwargs.setdefault("sender", self.owner)
        address = getattr(new_credential_manager, "address", new_credential_manager)
        return self.vault.set_credential_manager(to_evm_address(address), **tx_kwargs)

    async def set_administrators(
        self,
        admin_keys: list[str] | None = None,
        withdrawal_quorum: int | None = None,
        **tx_kwargs,
    ) -> Any:
        """
        Register the connected clearing-engine as a valid deposit vault admin.
        Requires being the vault contract owner.
        """
        tx_kwargs.setdefault("sender", self.owner)

        if admin_keys is None:
            if self.ce is None:
                raise ValueError("Either admin_key or self.ce must be specified")

            admin_keys = [await self.ce.admin.get_verifying_key()]

        addresses = [public_key_to_address(k) for k in admin_keys]

        if withdrawal_quorum is None:
            withdrawal_quorum = len(addresses)

        tx = self.vault.setAdministrators(addresses, withdrawal_quorum, **tx_kwargs)
        return tx

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

            await wait_for_condition(
                update_fn=lambda: ce.admin_settlements.update_approved_settlers(
                    self.chain_id, self.vault.address
                ),
                get_fn=lambda: ce.admin_settlements.get_approved_settlers(self.chain_id),
                check_fn=lambda settlers: settler in settlers,
                timeout=10,
                interval=1,
                error_msg="Settler approval failed.",
            )

        return tx

    async def register_depositor(self, depositor: Any) -> Any:
        depositor = self.backend.convert_address(depositor)
        return self.vault.setDepositorStatus(depositor, True, sender=self.owner)
