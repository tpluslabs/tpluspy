from typing import TYPE_CHECKING

from ape.exceptions import ContractNotFoundError, ProjectError
from ape.utils.basemodel import ManagerAccessMixin

from tplus.evm.abi import get_erc20_type

if TYPE_CHECKING:
    from ape.api import AccountAPI
    from ape.contracts import ContractContainer, ContractInstance
    from ape.managers.project import Project


# Copied from tpluslabs/tplus-contracts README.md.
TPLUS_DEPLOYMENTS = {
    11155111: {
        "Registry": "0x6DF956123aa80eBD5178d4d579c810ff352dF724",
        "DepositVault": "0x8800A71ad5201F7F3Cc519A20C6cDf8c29297EA3",
    }
}


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

    def __init__(self, name: str):
        self._deployments: dict[int, ContractInstance] = {}
        self._name = name

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
        return self.get_contract()

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
            raise ValueError(f"{self._name} not deployed on chain '{chain_id}'.")

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
            address = self.network_manager.ethereum.decode_address(itm.assetAddress)

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


class DepositVault(TPlusContract):
    def __init__(self):
        super().__init__("DepositVault")


registry = Registry()
vault = DepositVault()
