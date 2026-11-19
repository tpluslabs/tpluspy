from pydantic import BaseModel

from tplus.model.council import CouncilEnvelope, CouncilRequest
from tplus.model.types import ChainID
from tplus.utils.bincode import encode_u64


class ApprovalDurations(BaseModel):
    """How long one chain's withdrawal and settlement approvals stay executable."""

    withdrawal_secs: int
    settlement_secs: int


class ApprovalDurationChainMap(BaseModel):
    per_chain: dict[ChainID, ApprovalDurations]

    def to_bincode(self) -> bytes:
        """The bincode `ApprovalDurationChainMap` the council signs."""
        encoded = encode_u64(len(self.per_chain))
        for chain_id in sorted(self.per_chain):
            durations = self.per_chain[chain_id]
            encoded += chain_id.to_bytes()
            encoded += encode_u64(durations.withdrawal_secs) + encode_u64(durations.settlement_secs)

        return encoded


class SetApprovalDurationsPayload(CouncilEnvelope):
    approval_durations: ApprovalDurationChainMap


SetApprovalDurationsRequest = CouncilRequest[SetApprovalDurationsPayload]
