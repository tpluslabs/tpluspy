from pydantic import BaseModel

from tplus.model.asset_identifier import AssetAddress
from tplus.model.chain_address import ChainAddress
from tplus.model.types import ChainID


class RebalancingBacking(BaseModel):
    """One token of ``GET /registry/rebalancing-backing``, in its own units at 18 decimals: the
    anchor an outgoing approval set, if any, its admitted backing, what its approved payouts will
    take out, what stays once they do, and the free and locked parts of that backing. The three
    backing amounts are ``None`` while the clearing engine cannot price the token."""

    token: AssetAddress
    anchor: int | None
    ingested: int | None
    approved_outflows: int | None
    available: int | None
    admitted_balance: int
    locked_admitted_balance: int


class ChildManager(BaseModel):
    """A child credential manager the clearing engine's credential manager lists."""

    routing_id: int
    vm_id: int
    manager: str

    @property
    def chain_address(self) -> ChainAddress:
        chain_id = ChainID.from_parts(self.routing_id, self.vm_id)
        return ChainAddress.from_str(f"{self.manager.removeprefix('0x')}@{chain_id}")
