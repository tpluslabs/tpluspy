import os
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Optional, cast

import yaml
from ape.exceptions import ContractLogicError, ContractNotFoundError, ProjectError
from ape.types.address import AddressType
from ape.utils.basemodel import ManagerAccessMixin
from eth_pydantic_types.hex.bytes import HexBytes, HexBytes32

from tplus.evm.abi import get_erc20_type
from tplus.evm.constants import REGISTRY_ADDRESS
from tplus.evm.eip712 import Domain
from tplus.evm.exceptions import ContractNotExists
from tplus.model.asset_identifier import ChainAddress
from tplus.model.types import UserPublicKey
from tplus.utils.bytes32 import to_bytes32

if TYPE_CHECKING:
    from ape.api.accounts import AccountAPI
    from ape.api.transactions import ReceiptAPI
    from ape.contracts.base import ContractContainer, ContractInstance
    from ape.managers.project import LocalProject, Project

CHAIN_MAP = {
    1: "ethereum:mainnet",
    11155111: "ethereum:sepolia",
    42161: "arbitrum:mainnet",
    421614: "arbitrum:sepolia",
}
NETWORK_MAP = {
    "ethereum": {
        "mainnet": 1,
        "sepolia": 11155111,
    },
    "arbitrum": {
        "mainnet": 42161,
        "sepolia": 421614,
    },
}
DEFAULT_DEPLOYMENTS: dict = {42161: {"Registry": REGISTRY_ADDRESS}}


class TplusDeployments:
    """
    Reads the deployments from the ape-config file in the tplus-contracts
    repo. This saves 1 place at least where we have to remember to update
    new deployment addresses.
    """

    @cached_property
    def deployments(self) -> dict:
        contracts_path = Path(
            os.environ.get("TPLUS_CONTRACTS_PATH", "~/tplus/tplus-contracts")
        ).expanduser()
        file = contracts_path / "ape-config.yaml"

        if not file.is_file():
            return DEFAULT_DEPLOYMENTS

        registered = yaml.safe_load(file.read_text())["deployments"]
        result = {}

        for ecosystem, network_deployments in registered.items():
            for network, deployments in network_deployments.items():
                if len(deployments) == 0:
                    continue

                elif not (chain_id := NETWORK_MAP.get(ecosystem, {}).get(network)):
                    continue

                for deployment in deployments:
                    result.setdefault(chain_id, {})
                    result[chain_id][deployment["contract_type"]] = deployment["address"]

        return result

    def __getitem__(self, contract_name: str):
        return self.deployments[contract_name]

    def get(self, item, default=None):
        return self.deployments.get(item, default)


TPLUS_DEPLOYMENTS = TplusDeployments()


def load_tplus_contracts_project() -> "LocalProject":
    """
    Loads the Ape project containing the Solidity contracts for tplus.
    If you are in the tplus-contracts repo, it detects that and loads that way.
    Else, it checks all Ape installed dependencies. If it is not installed, it will fail.
    Install the tplus-contracts project by running ``ape pm install tpluslabs/tplus-contracts``.
    """
    if ManagerAccessMixin.local_project.name == "tplus-contracts":
        # Working from the t+ contracts repo
        return ManagerAccessMixin.local_project

    # Load the project from dependencies.
    available_versions = ManagerAccessMixin.local_project.dependencies["tplus-contracts"]
    if not (version_key := next(iter(available_versions), None)):
        raise ProjectError("Please install the t+ contracts project")

    project = available_versions[version_key]
    project.load_contracts()  # Ensure is compiled.
    return project


def load_tplus_contract_container(name: str) -> "ContractContainer":
    project = load_tplus_contracts_project()
    return project.get_contract(name)


def get_dev_default_owner() -> "AccountAPI":
    return ManagerAccessMixin.account_manager.test_accounts[0]


class TPlusMixin(ManagerAccessMixin):
    """
    A mixin for access to relevant t+ constructs.
    """

    @property
    def tplus_contracts_project(self) -> "Project":
        """
        The t+ contacts project. This will fail if Ape is not able to
        download and cache the contracts project from GitHub. See pyproject.toml
        Ape config for current specification.
        """
        return load_tplus_contracts_project()


class TPlusContract(TPlusMixin):
    """
    An abstraction around a t+ contract.
    """

    NAME: ClassVar[str] = ""

    def __init__(
        self,
        default_deployer: Optional["AccountAPI"] = None,
        chain_id: int | None = None,
        address: str | None = None,
    ) -> None:
        self._deployments: dict[int, ContractInstance] = {}
        self._default_deployer = default_deployer
        self._chain_id = chain_id
        self._address = address

        if address is not None and chain_id is not None:
            self._deployments[chain_id] = self._contract_container.at(address)

    @classmethod
    def deploy(cls, deployer: "AccountAPI") -> "TPlusContract":
        contract_container = load_tplus_contract_container(cls.NAME)
        instance = deployer.deploy(contract_container)
        chain_id = cls.chain_manager.chain_id
        return cls(default_deployer=deployer, chain_id=chain_id, address=instance.address)

    @classmethod
    def deploy_dev(cls):
        owner = get_dev_default_owner()
        return cls.deploy(owner)

    def __repr__(self) -> str:
        return f"<{self.name}>"

    def __getattr__(self, attr_name: str):
        try:
            # First, try a regular attribute on the class
            return self.__getattribute__(attr_name)
        except AttributeError:
            # Resort to something defined on the contract.
            return getattr(self.contract, attr_name)

    @property
    def name(self) -> str:
        return self.__class__.NAME

    @property
    def address(self) -> str:
        if address := self._address:
            return address

        chain_id = self._chain_id or self.chain_manager.chain_id
        return self.get_address(chain_id=chain_id)

    @property
    def _contract_container(self) -> "ContractContainer":
        return self.tplus_contracts_project.get_contract(self.name)

    @property
    def contract(self) -> "ContractInstance":
        """
        The contract instance at the currently connected chain.
        """
        try:
            return self.get_contract()
        except ContractNotExists:
            if self.chain_manager.provider.network.is_local:
                # If simulating, deploy it now.
                return self.deploy_dev()

            raise  # This error.

    @property
    def default_deployer(self) -> "AccountAPI":
        if deployer := self._default_deployer:
            return deployer

        elif self._default_deployer is None and self.network_manager.provider.network.is_local:
            deployer = self.account_manager.test_accounts[0]
            self._default_deployer = deployer
            return deployer

        raise ValueError(f"Cannot deploy '{self.name}' - No default deployer configured.")

    def set_chain(self, chain_id: int):
        self._chain_id = chain_id

    def get_contract(self, chain_id: int | None = None) -> "ContractInstance":
        """
        Load a contact instance for the given chain ID. Defaults to currently
        connected chain.

        Args:
            chain_id (int | None): The chain ID. Defaults to currently connected
              chain.

        Returns:
            ContractInstance
        """
        chain_id = chain_id or self._chain_id or self.chain_manager.chain_id
        if chain_id in self._deployments:
            # Get previously cached instance.
            return self._deployments[chain_id]

        address = self.get_address(chain_id=chain_id)
        contract_container = self._contract_container.at(address)

        # Cache for next time.
        self._deployments[chain_id] = contract_container

        return contract_container

    def get_address(self, chain_id: int | None = None) -> str:
        if self._address and self._chain_id and chain_id == self._chain_id:
            return self._address

        chain_id = chain_id or self._chain_id or self.chain_manager.chain_id
        try:
            return TPLUS_DEPLOYMENTS[chain_id][self.name]
        except KeyError:
            raise ContractNotExists(f"{self.name} not deployed on chain '{chain_id}'.")


class Registry(TPlusContract):
    NAME = "Registry"

    def get_assets(self, chain_id: int | None = None) -> list["ContractInstance"]:
        connected_chain = self.chain_manager.chain_id
        if connected_chain != chain_id and chain_id == 11155111:
            with self.network_manager.ethereum.sepolia.use_default_provider():
                return self._get_assets()

        return self._get_assets()

    def _get_assets(self) -> list["ContractInstance"]:
        contract = self.contract
        data = contract.getAssets()
        res = []

        for itm in data:
            evm_address = HexBytes(itm.assetAddress)[:20]
            address = self.network_manager.ethereum.decode_address(evm_address)

            # Attempt to look up native contract.
            try:
                contract = self.chain_manager.contracts.instance_at(address)
            except ContractNotFoundError:
                contract_type = get_erc20_type()
                contract = self.chain_manager.contracts.instance_at(
                    address, contract_type=contract_type
                )

            res.append(contract)

        return res

    def set_asset(
        self,
        index: int,
        asset_address: HexBytes32 | AddressType,
        chain_id: int,
        max_deposit: int,
        sender=None,
    ) -> None:
        if isinstance(asset_address, str) and len(asset_address) <= 42:
            # Given EVM style address. Store as right-padded address.
            asset_address = to_bytes32(asset_address, pad="r")

        return self.contract.setAssetData(
            index, (asset_address, chain_id, max_deposit), sender=sender
        )

    def add_vault(self, address: AddressType, chain_id: int | None = None, **kwargs):
        if not isinstance(address, str):
            # Allow ENS or certain classes to work.
            address = self.conversion_manager.convert(address, AddressType)

        chain_id = self.chain_manager.chain_id if chain_id is None else chain_id
        return self.contract.addVault(address, chain_id, **kwargs)

    def get_vaults(self) -> list[tuple[bytes, int]]:
        return [(r.vaultAddress, r.chain) for r in self.contract.getVaults()]

    def get_evm_vaults(self) -> list[tuple[AddressType, int]]:
        result = []
        for res in self.get_vaults():
            addr = res[0]
            if addr[20:] == b"\x00" * 12:
                addr_bytes = addr[:20]
                addr_str = f"0x{addr_bytes.hex()}"

                # Checksum it.
                checksummed_addr = self.network_manager.ethereum.decode_address(addr_str)

                result.append((checksummed_addr, res[1]))

        return result


class DepositVault(TPlusContract):
    NAME = "DepositVault"

    def __getattr__(self, attr_name: str):
        if self._chain_id is None or attr_name in ("address",) or attr_name.startswith("_"):
            return super().__getattr__(attr_name)

        # Verify chain first.
        connected_chain = self.chain_manager.chain_id
        if connected_chain != self._chain_id:
            # Try to connect.
            if choice := CHAIN_MAP.get(connected_chain):
                with self.network_manager.parse_network_choice(choice):
                    # Run on this network.
                    return super().__getattribute__(attr_name)

            raise AttributeError(
                "Please connect to this vault's chain first. `with ape.networks...`."
            )

        return super().__getattr__(attr_name)

    @classmethod
    def from_chain_address(cls, chain_address: ChainAddress) -> "DepositVault":
        return cls(chain_id=chain_address.chain_id, address=chain_address.evm_address)

    def deposit(
        self, user: UserPublicKey, token: AddressType, amount: int, **tx_kwargs
    ) -> "ReceiptAPI":
        try:
            return self.contract.deposit(user, token, amount, **tx_kwargs)
        except ContractLogicError as err:
            if erc20_err_name := _decode_erc20_error(err.message):
                raise ContractLogicError(erc20_err_name) from err

            raise  # Error as-is.

    def execute_atomic_settlement(
        self,
        settlement: dict,
        user: UserPublicKey,
        data: HexBytes,
        signature: HexBytes,
        **tx_kwargs,
    ) -> "ReceiptAPI":
        try:
            return self.contract.executeAtomicSettlement(
                settlement, user, data, signature, **tx_kwargs
            )
        except ContractLogicError as err:
            if erc20_err_name := _decode_erc20_error(err.message):
                raise ContractLogicError(erc20_err_name) from err

            raise  # Error as-is.

    @classmethod
    def deploy(cls, deployer: "AccountAPI") -> "DepositVault":
        instance = super().deploy(deployer)

        # Set the domain separator.
        instance.set_domain_separator(deployer)

        return instance

    @classmethod
    def deploy_dev(cls, owner: "AccountAPI | None" = None) -> TPlusContract:
        """
        Deploy and set up a development vault.
        """
        owner = owner or cls.account_manager.test_accounts[0]
        contract = cast(DepositVault, cls.deploy(deployer=owner))

        # Set the owner as an admin who can approve settlements/withdrawals.
        # (we only do this in dev mode; irl the roles are different).
        contract.set_admin_status(owner, True, owner)

        return contract

    def set_admin_status(
        self, admin: "AddressType", status: bool, vault_owner: "AccountAPI"
    ) -> "ReceiptAPI":
        return self.contract.setAdmin(admin, status, sender=vault_owner)

    def set_domain_separator(
        self, vault_owner: "AccountAPI", domain_separator: bytes | None = None
    ) -> "ReceiptAPI":
        domain_separator = (
            domain_separator
            or Domain(
                _chainId_=self.chain_manager.chain_id,
                _verifyingContract_=self.address,
            )._domain_separator_
        )

        return self.contract.setDomainSeparator(domain_separator, sender=vault_owner)


def _decode_erc20_error(err: str) -> ContractLogicError | None:
    if err == "0x7939f424":
        # The sender likely didn't approve, or they don't have the tokens.
        return "TransferFromFailed()"

    elif err == "0x90b8ec18":
        # The sender likely doesn't have the tokens.
        return "TransferFailed()"

    return None


registry = Registry()
vault = DepositVault()
