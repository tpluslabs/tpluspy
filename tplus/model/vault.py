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


class RebalancingFeeQuote(BaseModel):
    """Reply of ``POST /registry/rebalancing-fee-quote``: every amount but ``amount`` is in
    canonical credits of the token's asset index at 18 decimals."""

    token: AssetAddress
    """Token representation quoted."""

    amount: int
    """Amount quoted, in the token's own units at 18 decimals."""

    fee: int
    """Rebalancing fee of paying ``amount`` out."""

    reward: int
    """Rebalancing reward of admitting ``amount``, before the reward haircut and the rebalancing
    fee account's balance cap it."""

    canonical_amount_in: int
    """Canonical amount a Funding account transfer in credits to the trading account for
    ``amount``: the value of ``amount``, rounded down, plus ``reward``. It counts ``reward``
    before the reward haircut and the rebalancing fee account's balance cap it, so the transfer
    can credit less."""

    canonical_amount_out: int
    """Canonical amount a Funding account transfer out debits from the trading account to pay
    ``amount`` out: the value of ``amount``, rounded up, plus the rebalancing fee of the tokens
    that value pays out. Rounding up can make those more than ``amount``, so the fee counted here
    can be higher than ``fee``."""


class ChildManager(BaseModel):
    """A child credential manager the clearing engine's credential manager lists."""

    routing_id: int
    vm_id: int
    manager: str

    @property
    def chain_address(self) -> ChainAddress:
        chain_id = ChainID.from_parts(self.routing_id, self.vm_id)
        return ChainAddress.from_str(f"{self.manager.removeprefix('0x')}@{chain_id}")
