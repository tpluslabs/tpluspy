from typing import TYPE_CHECKING

from ape.utils.basemodel import ManagerAccessMixin

if TYPE_CHECKING:
    from ape.contracts import ContractContainer, ContractInstance
    from ape.managers.project import Project


# Copied from tpluslabs/tplus-contracts README.md.
TPLUS_DEPLOYMENTS = {
    11155111: {
        "Registry": "0x47aEfEe8367C9bAC049B97D821E8Fcd1c75F7cD2",
        "DepositVault": "0xA56e0BE94Ea18d94dD68bFa786A4D96E3cA7DccD",
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
        return self.local_project.dependencies["tplus-contracts"]["main"]


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

        address = TPLUS_DEPLOYMENTS[chain_id][self._name]
        contract_container = self._contract_container.at(address)

        # Cache for next time.
        self._deployments[chain_id] = contract_container

        return contract_container


class Registry(TPlusContract):
    def __init__(self):
        super().__init__("Registry")


class DepositVault(TPlusContract):
    def __init__(self):
        super().__init__("DepositVault")
