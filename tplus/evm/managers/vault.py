from typing import TYPE_CHECKING

from ape.types.address import AddressType

from tplus.client import ClearingEngineClient
from tplus.evm.address import public_key_to_address
from tplus.evm.contracts import DepositVault
from tplus.evm.eip712 import Domain
from tplus.evm.managers.evm import ChainConnectedManager
from tplus.model.types import ChainID, UserPublicKey
from tplus.utils.timeout import wait_for_condition

if TYPE_CHECKING:
    from ape.api.accounts import AccountAPI
    from ape.api.transactions import ReceiptAPI
    from ape.contracts.base import ContractInstance


class VaultOwner(ChainConnectedManager):
    """
    This manager is for council use against the vault contract.
    It contains simpler operations for configuring vaults.
    """

    def __init__(
        self,
        owner: "AccountAPI",
        vault: DepositVault | None = None,
        chain_id: ChainID | None = None,
        clearing_engine: "ClearingEngineClient | None" = None,
    ):
        self.owner = owner
        self.chain_id = chain_id or ChainID.evm(self.chain_manager.chain_id)
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

    async def set_administrators(
        self,
        admin_keys: list[str] | None = None,
        withdrawal_quorum: int | None = None,
        **tx_kwargs,
    ) -> "ReceiptAPI":
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
        settler: UserPublicKey,
        executor: "AddressType | str | AccountAPI | ContractInstance",
        wait: bool = False,
        **tx_kwargs,
    ) -> "ReceiptAPI":
        """
        Allow a user to settler. Requires being the vault contract owner.
        """
        executor = self.conversion_manager.convert(executor, AddressType)
        tx_kwargs.setdefault("sender", self.owner)
        tx = self.vault.add_settler_executor(settler, executor, **tx_kwargs)

        if wait:
            if not (ce := self.ce):
                raise ValueError("Must have clearing_engine to wait for settler registration.")

            await wait_for_condition(
                update_fn=lambda: ce.settlements.update_approved_settlers(
                    self.chain_id, self.vault.address
                ),
                get_fn=lambda: ce.settlements.get_approved_settlers(self.chain_id),
                check_fn=lambda settlers: settler in settlers,
                timeout=10,
                interval=1,
                error_msg="Settler approval failed.",
            )

        return tx

    async def register_depositor(
        self, depositor: "AddressType | str | AccountAPI | ContractInstance"
    ) -> "ReceiptAPI":
        depositor = self.conversion_manager.convert(depositor, AddressType)
        return self.vault.setDepositorStatus(depositor, True, sender=self.owner)
