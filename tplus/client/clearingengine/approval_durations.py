"""Operator-committee signed per-chain approval durations."""

from collections.abc import Callable, Mapping

from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.approval_durations import (
    ApprovalDurationChainMap,
    SetApprovalDurationsPayload,
    SetApprovalDurationsRequest,
)
from tplus.model.council import build_council_request

SET_APPROVAL_DURATIONS_DOMAIN = b"tplus.ce.set_approval_durations.v1"


def build_set_approval_durations_request(
    durations: ApprovalDurationChainMap,
    signers: Mapping[str, Callable[[bytes], str]],
    threshold: int,
    min_seq: int,
    max_seq: int,
) -> SetApprovalDurationsRequest:
    return build_council_request(
        SetApprovalDurationsPayload,
        {"approval_durations": durations},
        SET_APPROVAL_DURATIONS_DOMAIN,
        durations.to_bincode(),
        signers,
        threshold,
        min_seq,
        max_seq,
    )


class ApprovalDurationsClient(BaseClearingEngineClient):
    async def get_approval_durations(self) -> ApprovalDurationChainMap:
        return ApprovalDurationChainMap.model_validate(await self._get("approval-durations"))

    async def set_approval_durations(
        self,
        durations: ApprovalDurationChainMap,
        signers: Mapping[str, Callable[[bytes], str]],
        threshold: int,
    ) -> None:
        """Submit the full per-chain map, replacing every chain's durations."""
        await self.post_council_request(
            "approval-durations/set",
            lambda min_seq, max_seq: build_set_approval_durations_request(
                durations, signers, threshold, min_seq, max_seq
            ).model_dump(mode="json"),
        )
