from pydantic import BaseModel

from tplus.model.chain_address import ChainAddress
from tplus.model.types import ChainID


class RebalancingBacking(BaseModel):
    """The clearing engine's rebalancing view of a token at 18 decimals: the anchor an outgoing
    approval set, if any, the backing the vault holds admitted to the asset, what its approved
    payouts will take out, and what stays once they do."""

    anchor: int | None
    ingested: int
    approved_outflows: int
    available: int


class ChildManager(BaseModel):
    """A child credential manager the clearing engine's credential manager lists."""

    routing_id: int
    vm_id: int
    manager: str

    @property
    def chain_address(self) -> ChainAddress:
        chain_id = ChainID.from_parts(self.routing_id, self.vm_id)
        return ChainAddress.from_str(f"{self.manager.removeprefix('0x')}@{chain_id}")
