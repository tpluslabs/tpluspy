from typing import TYPE_CHECKING

from tplus.evm.address import public_key_to_address
from tplus.evm.contracts import AddressType, CredentialManager, DepositVault
from tplus.evm.governance import to_operator_key
from tplus.evm.managers.evm import ChainConnectedManager
from tplus.model.asset_identifier import ChainAddress
from tplus.model.config import ChainConfig
from tplus.model.types import ChainID
from tplus.utils.timeout import wait_for_condition

if TYPE_CHECKING:
    from tplus.client.clearingengine import ClearingEngineClient
    from tplus.client.oms.assetregistry import AssetRegistryClient
    from tplus.evm.backends.base import EVMBackend


class CredentialManagerOwner(ChainConnectedManager):
    """
    Committee utilities for the credential manager: operations signed by the operator keys.
    """

    def __init__(
        self,
        signers: list,
        credential_manager: CredentialManager | None = None,
        chain_id: ChainID | None = None,
        clearing_engine: "ClearingEngineClient | None" = None,
        asset_registry_client: "AssetRegistryClient | None" = None,
        *,
        backend: "EVMBackend | None" = None,
    ):
        self._set_backend(backend)
        self.operator_keys = [to_operator_key(signer) for signer in signers]
        self.chain_id = chain_id or ChainID.evm(self.backend.chain_id)

        if credential_manager is not None:
            self.credential_manager = credential_manager
        else:
            # Prefer the CE-registered deployment so we don't accidentally trip
            # the local-network auto-redeploy path.
            try:
                self.credential_manager = CredentialManager.from_ce_address(backend=self.backend)
            except ValueError:
                self.credential_manager = CredentialManager(
                    chain_id=self.chain_id, backend=self.backend
                )

        self.ce = clearing_engine
        self.asset_registry = asset_registry_client

    @property
    def governance_nonce(self) -> int:
        return self.credential_manager.governance_nonce

    async def add_vault(
        self,
        vault: ChainAddress | DepositVault,
        chain_config: ChainConfig,
        wait: bool = False,
        *,
        sender: AddressType,
        **tx_kwargs,
    ):
        """
        Register a vault through a committee-signed operation.

        Args:
            vault (ChainAddress): The address and chain of the vault.
            chain_config (ChainConfig): The chain configuration for the chain the vault is deployed on.
            wait (bool): If true and the CE exists, will wait for the vault to be registered in the CE.
            sender: The funded account that sends the operation.
            tx_kwargs: Additional tx kwargs, such as ``gas``.

        Returns:
            The operation ID.
        """
        if isinstance(vault, DepositVault):
            vault = vault.chain_address

        op_id = self.credential_manager.add_vault(
            vault, chain_config, operator_keys=self.operator_keys, sender=sender, **tx_kwargs
        )

        if wait:
            if not (ce := self.ce):
                raise ValueError("Must have clearing_engine to wait for vault registration.")
            if self.asset_registry is None:
                raise ValueError(
                    "Must have OMS asset_registry_client to wait for vault registration."
                )

            await wait_for_condition(
                update_fn=lambda: ce.vaults.update(),
                get_fn=lambda: self.asset_registry.get_vaults(),
                # cond: checks if the vault address is part any of the ChainAddress returned.
                check_fn=lambda vaults: vault in vaults,
                timeout=10,
                error_msg=f"Vault registration failed (vault={vault}).",
            )

        return op_id

    async def attest_signer(
        self, signer_key: str | None = None, *, sender: AddressType, **tx_kwargs
    ) -> bool:
        """
        Attest the clearing engine's signer for the first operator key over a mock quote, on a
        manager with no attestation verifier. Does nothing while the operator already holds it.

        Args:
            signer_key: The signer's public key. Defaults to the connected clearing engine's.
            sender: The funded account that sends the attestation and executes the rotation.
            tx_kwargs: Additional tx kwargs, such as ``gas``.

        Returns:
            Whether a new key was attested.
        """
        if signer_key is None:
            if self.ce is None:
                raise ValueError("Either signer_key or clearing_engine must be specified")

            signer_key = await self.ce.admin.get_verifying_key()

        return self.credential_manager.attest_signer(
            self.operator_keys[0], public_key_to_address(signer_key), sender=sender, **tx_kwargs
        )

    def ensure_intra_chain_strategy(
        self, chain_id: ChainID | None = None, *, sender: AddressType, **tx_kwargs
    ) -> AddressType | None:
        """
        Register the strategy that delivers snapshots to a vault on the manager's own chain,
        unless ``chain_id`` already has one.

        Returns:
            The new strategy's address, or None while ``chain_id`` already has a strategy.
        """
        chain_id = chain_id or self.chain_id
        registered = self.credential_manager.adminUpdateStrategies(
            chain_id.routing_id, chain_id.vm_id
        )
        if int(str(registered), 16) != 0:
            return None

        return self.credential_manager.register_intra_chain_strategy(
            chain_id, operator_keys=self.operator_keys, sender=sender, **tx_kwargs
        )

    def sync_vault(self, chain_id: ChainID | None = None, *, sender: AddressType, **tx_kwargs):
        """Deliver the manager's committed governance snapshot to the vault on ``chain_id``."""
        return self.credential_manager.sync_vault_governance_snapshot(
            chain_id or self.chain_id, sender=sender, **tx_kwargs
        )
