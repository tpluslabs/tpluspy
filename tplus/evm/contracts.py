import os
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

import yaml
from ape.exceptions import ContractNotFoundError, ProjectError
from ape.types import AddressType
from ape.utils.basemodel import ManagerAccessMixin
from eth_pydantic_types.hex.bytes import HexBytes, HexBytes32

from tplus.evm.abi import get_erc20_type
from tplus.evm.exceptions import ContractNotExists
from tplus.evm.utils import to_bytes32

if TYPE_CHECKING:
    from ape.api import AccountAPI
    from ape.contracts import ContractContainer, ContractInstance
    from ape.managers.project import Project


class TplusDeployments:
    """
    Reads the deployments from the ape-config file in the tplus-contracts
    repo. This saves 1 place at least where we have to remember to update
    new deployment addresses.
    """

    @cached_property
    def deployments(self):
        contracts_path = Path(
            os.environ.get("TPLUS_CONTRACTS_PATH", "~/tplus/tplus-contracts")
        ).expanduser()
        file = contracts_path / "ape-config.yaml"
        registered = yaml.safe_load(file.read_text())["deployments"]
        result = {11155111: {}, 421614: {}}

        for eco, net, chain in [("ethereum", "sepolia", 11155111), ("arbitrum", "sepolia", 421614)]:
            for itm in registered[eco][net]:
                result[chain][itm["contract_type"]] = itm["address"]

        return result

    def __getitem__(self, item):
        return self.deployments[item]

    def get(self, item, default=None):
        return self.deployments.get(item, default=default)


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

    def __init__(self, name: str, default_deployer: Optional["AccountAPI"] = None) -> None:
        self._deployments: dict[int, ContractInstance] = {}
        self._name = name
        self._default_deployer = default_deployer

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
        chain_id = chain_id or self.chain_manager.chain_id
        if chain_id in self._deployments:
            # Get previously cached instance.
            return self._deployments[chain_id]

        try:
            addresses = TPLUS_DEPLOYMENTS[chain_id]
        except KeyError:
            raise ContractNotExists(f"{self._name} not deployed on chain '{chain_id}'.")

        contract_container = self._contract_container.at(addresses[self._name])

        # Cache for next time.
        self._deployments[chain_id] = contract_container

        return contract_container

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
        asset_address: Union[HexBytes32, AddressType],
        chain_id: int,
        max_deposit: int,
        sender=None,
    ) -> None:
        if isinstance(asset_address, str) and len(asset_address) <= 42:
            # Given EVM style address.
            asset_address = to_bytes32(asset_address)

        return self.contract.setAssetData(
            index, (asset_address, chain_id, max_deposit), sender=sender
        )


class DepositVault(TPlusContract):
    def __init__(self):
        super().__init__("DepositVault")


registry = Registry()
vault = DepositVault()
