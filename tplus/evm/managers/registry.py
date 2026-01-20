from typing import TYPE_CHECKING

from tplus.evm.contracts import Registry
from tplus.evm.managers.evm import ChainConnectedManager

if TYPE_CHECKING:
    from ape.api.accounts import AccountAPI

    from tplus.client.clearingengine import ClearingEngineClient


class RegistryOwner(ChainConnectedManager):
    """
    For registry (`Registry.sol`) operations using the owner of the contract.
    """

    def __init__(
        self,
        owner: "AccountAPI",
        registry: Registry | None = None,
        chain_id: int | None = None,
        clearing_engine: "ClearingEngineClient | None" = None,
    ):
        self.owner = owner
        self.chain_id = chain_id or self.chain_manager.chain_id

        if registry is None:
            self.registry = Registry(chain_id=self.chain_id)
        else:
            self.registry = registry

        self.ce = clearing_engine
