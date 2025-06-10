from typing import TYPE_CHECKING, Optional, Union

from ape.exceptions import ContractNotFoundError, ProjectError
from ape.utils.basemodel import ManagerAccessMixin
from eth_pydantic_types.hex.bytes import HexBytes32
from ape.types import AddressType

from tplus.evm.abi import get_erc20_type
from tplus.evm.exceptions import ContractNotExists
from tplus.evm.utils import address_to_bytes32

if TYPE_CHECKING:
    from ape.api import AccountAPI
    from ape.contracts import ContractContainer, ContractInstance
    from ape.managers.project import Project


# Copied from tpluslabs/tplus-contracts README.md.
TPLUS_DEPLOYMENTS = {
    11155111: {
        "Registry": "0xD32DFD142A88E38233757DbE9d8681ac83D857d1",
        "DepositVault": "0x8a54c3bC74854Dd908437f20f77a61FcC082AA3B",
    },
    421614: {
        "Registry": "0x75E435c12A0f07073dc35832F72D576dBcb9d05c",
        "DepositVault": "0x47aEfEe8367C9bAC049B97D821E8Fcd1c75F7cD2",
    },
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

    def set_asset(self, index: int, asset_address: Union[HexBytes32, AddressType], chain_id: int, max_deposit: int, sender=None) -> None:
        if isinstance(asset_address, str) and len(asset_address) <= 42:
            # Given EVM style address.
            asset_address = address_to_bytes32(asset_address)

        return self.contract.setAssetData(index, (asset_address, chain_id, max_deposit), sender=sender)


class DepositVault(TPlusContract):
    def __init__(self):
        super().__init__("DepositVault")


registry = Registry()
vault = DepositVault()
