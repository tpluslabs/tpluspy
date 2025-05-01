from typing import TYPE_CHECKING

from ape.exceptions import ContractNotFoundError
from ape.utils.basemodel import ManagerAccessMixin
from ape_tokens.types import ERC20
from eth_pydantic_types import AddressType
from ethpm_types import MethodABI
from ethpm_types.abi import ABIType

if TYPE_CHECKING:
    from ape.api import AccountAPI
    from ape.contracts import ContractContainer, ContractInstance
    from ape.managers.project import Project


# Copied from tpluslabs/tplus-contracts README.md.
TPLUS_DEPLOYMENTS = {
    11155111: {
        "Registry": "0x47aEfEe8367C9bAC049B97D821E8Fcd1c75F7cD2",
        "DepositVault": "0xA56e0BE94Ea18d94dD68bFa786A4D96E3cA7DccD",
    }
}

MINT_METHOD = MethodABI(
    type="function",
    name="mint",
    stateMutability="nonpayable",
    inputs=[
        ABIType(name="to", type="address", components=None, internal_type="address"),
        ABIType(name="amount", type="uint256", components=None, internal_type="uint256"),
    ],
    outputs=[],
)


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
        versions = self.local_project.dependencies["tplus-contracts"]
        project = versions[next(iter(versions))]
        project.load_contracts()
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
        # [getAssets_return(assetAddress=HexBytes('0x00000000000000000000000062622e77d1349face943c6e7d5c01c61465fe1dc'), chainId=11155111, maxDeposits=100), getAssets_return(assetAddress=HexBytes('0x00000000000000000000000058372ab62269a52fa636ad7f200d93999595dcaf'), chainId=11155111, maxDeposits=100)]
        for itm in data:
            address = self.network_manager.ethereum.decode_address(itm.assetAddress)

            # Attempt to look up native contract.
            try:
                contract = self.chain_manager.contracts.instance_at(address)
            except ContractNotFoundError:
                contract_type = get_test_erc20_type()
                contract = self.chain_manager.contracts.instance_at(
                    address, contract_type=contract_type
                )

            res.append(contract)

        return res


class DepositVault(TPlusContract):
    def __init__(self):
        super().__init__("DepositVault")


def get_erc20_type():
    return ERC20.model_copy()


def get_test_erc20_type():
    contract_type = ERC20.model_copy()
    contract_type.abi.append(MINT_METHOD)
    return contract_type


def address_to_bytes32(address: str | AddressType) -> bytes:
    addr_bytes = bytes.fromhex(address[2:])
    return addr_bytes.rjust(32, b"\x00")


registry = Registry()
vault = DepositVault()
