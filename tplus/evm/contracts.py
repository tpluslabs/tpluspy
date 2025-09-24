import os
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import yaml
from ape.exceptions import ContractLogicError, ContractNotFoundError, ProjectError
from ape.types import AddressType
from ape.utils.basemodel import ManagerAccessMixin
from eth_pydantic_types.hex.bytes import HexBytes, HexBytes32

from build.lib.tplus.model.types import UserPublicKey
from tplus.evm.abi import get_erc20_type
from tplus.evm.constants import REGISTRY_ADDRESS
from tplus.evm.exceptions import ContractNotExists
from tplus.model.asset_identifier import ChainAddress
from tplus.utils.bytes32 import to_bytes32

if TYPE_CHECKING:
    from ape.api import AccountAPI
    from ape.contracts import ContractContainer, ContractInstance
    from ape.managers.project import Project


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
        if self.local_project.name == "tplus-contracts":
            # Working from the t+ contracts repo
            return self.local_project

        # Load the project from dependencies.
        available_versions = self.local_project.dependencies["tplus-contracts"]
        if not (version_key := next(iter(available_versions), None)):
            raise ProjectError("Please install the t+ contracts project")

        project = available_versions[version_key]
        project.load_contracts()  # Ensure is compiled.
        return project


class TPlusContract(TPlusMixin):
    """
    An abstraction around a t+ contract.
    """

    def __init__(
        self,
        name: str,
        default_deployer: Optional["AccountAPI"] = None,
        chain_id: int | None = None,
        address: str | None = None,
    ) -> None:
        self._deployments: dict[int, ContractInstance] = {}
        self._name = name
        self._default_deployer = default_deployer
        self._chain_id = chain_id
        self._address = address

    def __repr__(self) -> str:
        return f"<{self._name}>"

    def __getattr__(self, attr_name: str):
        try:
            # First, try a regular attribute on the class
            return self.__getattribute__(attr_name)
        except AttributeError:
            # Resort to something defined on the contract.
            return getattr(self.contract, attr_name)

    @property
    def address(self) -> str:
        if address := self._address:
            return address

        chain_id = self._chain_id or self.chain_manager.chain_id
        return self.get_address(chain_id=chain_id)

    @property
    def _contract_container(self) -> "ContractContainer":
        return self.tplus_contracts_project.get_contract(self._name)

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
                return self.deploy(self.default_deployer)

            raise  # This error.

    @property
    def default_deployer(self) -> "AccountAPI":
        if deployer := self._default_deployer:
            return deployer

        elif self._default_deployer is None and self.network_manager.provider.network.is_local:
            deployer = self.account_manager.test_accounts[0]
            self._default_deployer = deployer
            return deployer

        raise ValueError(f"Cannot deploy '{self._name}' - No default deployer configured.")

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
            return TPLUS_DEPLOYMENTS[chain_id][self._name]
        except KeyError:
            raise ContractNotExists(f"{self._name} not deployed on chain '{chain_id}'.")

    def deploy(self, deployer: "AccountAPI") -> "TPlusContract":
        instance = deployer.deploy(self._contract_container)
        chain_id = self.chain_manager.chain_id
        self._deployments[chain_id] = instance
        return instance


class Registry(TPlusContract):
    def __init__(self):
        super().__init__("Registry")

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

    def get_vaults(self) -> list[tuple[AddressType, int]]:
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
    def __init__(self, chain_id: int | None = None, address: str | None = None) -> None:
        super().__init__("DepositVault", chain_id=chain_id, address=address)

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
        return cls(chain_address.chain_id, chain_address.evm_address)

    def approve(self, user: UserPublicKey, token: AddressType, amount: int, **tx_kwargs) -> None:
        try:
            return self.contract.approve(user, token, amount, tx_kwargs)
        except ContractLogicError as err:
            if erc20_er := _decode_erc20_error(err):
                raise erc20_er

            raise  # Error as-is.

    def execute_atomic_settlement(
        self,
        settlement: dict,
        user: UserPublicKey,
        data: HexBytes,
        signature: HexBytes,
        **tx_kwargs,
    ) -> None:
        try:
            return self.contract.execute_atomic_settlement(
                settlement, user, data, signature, **tx_kwargs
            )
        except ContractLogicError as err:
            if erc20_er := _decode_erc20_error(err):
                raise erc20_er

            raise  # Error as-is.


def _decode_erc20_error(err: ContractLogicError) -> ContractLogicError | None:
    if err.message == "0x7939f424":
        return ContractLogicError("TransferFromFailed").from_error(err)

    return None


registry = Registry()
vault = DepositVault()
