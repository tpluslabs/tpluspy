from functools import cached_property
from typing import TYPE_CHECKING

from ape.utils.basemodel import ManagerAccessMixin
from eip712 import EIP712Domain, EIP712Message
from eth_abi import encode
from eth_pydantic_types.abi import bytes32, uint256
from eth_utils import keccak

from tplus.evm.contracts import CredentialManager, DepositVault
from tplus.model.asset_identifier import ChainAddress
from tplus.model.config import ChainConfig
from tplus.model.types import ChainID
from tplus.utils.timeout import wait_for_condition

if TYPE_CHECKING:
    from ape.api.accounts import AccountAPI
    from ape.types.address import AddressType

    from tplus.client.clearingengine import ClearingEngineClient


OP_ADD_VAULT = keccak(b"OP_ADD_VAULT")


def create_domain(credential_manager: "AddressType", chain_id: int | ChainID) -> EIP712Domain:
    if isinstance(chain_id, ChainID):
        chain_id = chain_id.vm_id

    return EIP712Domain(
        name="CredentialManager",
        version="1",
        chainId=chain_id,
        verifyingContract=credential_manager,
    )


def create_action(
    op_type: bytes, params_hash: bytes, nonce: int, domain: EIP712Domain
) -> EIP712Message:
    class Action(EIP712Message):
        eip712_domain = domain

        opType: bytes32
        paramsHash: bytes32
        nonce: uint256

    return Action(opType=op_type, paramsHash=params_hash, nonce=nonce)


def sort_accounts(accounts: list["AccountAPI"]) -> list["AccountAPI"]:
    return sorted(accounts, key=lambda a: int(a.address, 16))


class CredentialManagerOwner(ManagerAccessMixin):
    """
    Owner utilities for the credential manager
    """

    def __init__(
        self,
        admin: "AddressType",
        signers: list["AccountAPI"],
        credential_manager: CredentialManager | None = None,
        chain_id: ChainID | None = None,
        clearing_engine: "ClearingEngineClient | None" = None,
    ):
        self.admin = admin
        self.signers = signers
        self.chain_id = chain_id or ChainID.evm(self.chain_manager.chain_id)

        if credential_manager is None:
            self.credential_manager = CredentialManager(chain_id=self.chain_id)
        else:
            self.credential_manager = credential_manager

        self.ce = clearing_engine

    @property
    def governance_nonce(self) -> int:
        return self.credential_manager.governance_nonce

    @cached_property
    def domain(self) -> EIP712Domain:
        return create_domain(self.credential_manager.address, self.chain_id)

    async def add_vault(
        self,
        vault: ChainAddress | DepositVault,
        chain_config: ChainConfig,
        wait: bool = False,
        **tx_kwargs,
    ):
        """
        Add a vault to the registry.

        Args:
            vault (ChainAddress): The address and chain of the vault.
            chain_config (ChainConfig): The chain configuration for the chain the vault is deployed on.
            wait (bool): If true and the CE exists, will wait for the vault to be registered in the CE.
            tx_kwargs: Additional tx kwargs.

        Returns:
            ReceiptAPI
        """
        if isinstance(vault, DepositVault):
            vault = vault.chain_address

        sender = tx_kwargs["sender"]
        if sender == self.admin:
            signers = []
            signatures = []
        else:
            params_hash = self._encode_add_vault_params(vault, chain_config)
            signers = sort_accounts(self.signers)
            signatures = self._get_signatures(
                OP_ADD_VAULT,
                params_hash,
            )

        tx = self.credential_manager.add_vault(
            vault, chain_config, signers, signatures, **tx_kwargs
        )

        if wait:
            if not (ce := self.ce):
                raise ValueError("Must have clearing_engine to wait for vault registration.")

            await wait_for_condition(
                update_fn=lambda: ce.vaults.update(),
                get_fn=lambda: ce.vaults.get(),
                # cond: checks if the vault address is part any of the ChainAddress returned.
                check_fn=lambda vaults: any(vault in vault_ca for vault_ca in vaults),
                timeout=10,
                interval=1,
                error_msg="Vault registration failed.",
            )

        return tx

    def _encode_add_vault_params(self, vault: ChainAddress, chain_config: ChainConfig) -> bytes:
        encoded = encode(
            ["uint256", "uint256", "address", "(" + ",".join(chain_config.abi_types) + ")"],
            [
                vault.chain_id.routing_id,
                vault.chain_id.vm_id,
                vault.evm_address,
                tuple(chain_config.abi_values),
            ],
        )
        return keccak(encoded)

    def _get_signatures(
        self,
        op_type: bytes,
        params_hash: bytes,
        count: int | None = None,
    ) -> list[bytes]:
        action = self._create_action(op_type, params_hash)
        signers = sort_accounts(self.signers)
        if count is None:
            count = len(self.signers)

        signatures = []
        for acct in signers[:count]:
            if signature := acct.sign_message(action):
                signatures.append(signature.encode_rsv())

        return signatures

    def _create_action(
        self,
        op_type: bytes,
        params_hash: bytes,
        nonce: int | None = None,
    ) -> EIP712Message:
        if nonce is None:
            nonce = self.governance_nonce

        return create_action(op_type, params_hash, nonce, self.domain)
