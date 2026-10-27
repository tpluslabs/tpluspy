from typing import Any

from pydantic import BaseModel, field_validator

from tplus.model.approval import SettlementApproval
from tplus.model.asset_identifier import Address32, AssetIdentifier
from tplus.model.settlement import SettlementMode
from tplus.model.types import ChainID, UserPublicKey


class SyncSettlementQuote(BaseModel):
    """
    One of the caller's own quotes a sync fill crossed, paired with the trade id of the
    fill against it. ``trade_id`` is ``None`` when the match carried none — the pairing
    is why a quote without one does not shift the ids of the quotes after it.
    """

    order_id: str
    trade_id: int | None = None


class SyncSettlementApproved(BaseModel):
    """
    The CE approved the settlement derived from a sync taker fill. Delivered on the
    ``/sync/pending_settlements`` stream to the settler (the maker), who executes it on chain
    through its registered executor. Amounts are in the tokens' native on-chain decimals,
    exactly as covered by ``approval``.
    """

    asset: AssetIdentifier
    maker_quotes: list[SyncSettlementQuote] = []
    """The settler's own quotes the fill crossed, each with its trade id; the taker is only
    known by ``tplus_user``."""
    tplus_user: UserPublicKey
    sub_account_index: int
    settler: UserPublicKey
    mode: SettlementMode
    asset_in: Address32
    amount_in: int
    asset_out: Address32
    amount_out: int
    chain_id: ChainID
    approval: SettlementApproval
    timestamp_ns: int

    @field_validator("amount_in", "amount_out", mode="before")
    @classmethod
    def _parse_amount(cls, value: Any) -> int:
        return int(value)


COUNTERPARTY_AT_FAULT = "counterparty_at_fault"
"""``SyncSettlementFailure.reason`` when the other party's order or balance caused it."""


class SyncSettlementFailure(BaseModel):
    """
    A sync fill the caller is a party to will not settle: the CE refused it, or the
    approval deadline passed with no execution on chain. Delivered on the
    ``/sync/pending_settlements`` stream to both parties, each receiving its own view:
    only its own orders, and ``details`` only when its own order or balance caused it.
    Nothing settles and the book restores none of the consumed quote; a sync leg emits
    no trade, so this is the outcome.
    """

    asset: AssetIdentifier
    taker_order_id: str | None = None
    """The caller's taker order, when the caller took the fill."""
    maker_quotes: list[SyncSettlementQuote] = []
    """The caller's own quotes the fill crossed, when the caller made it."""
    reason: str
    """Snake-case reason code, or ``counterparty_at_fault``."""
    details: str | None = None
    """Why, only when the caller's own order or balance caused it."""
    timestamp_ns: int

    @property
    def counterparty_at_fault(self) -> bool:
        """Whether the other party's order or balance caused this."""
        return self.reason == COUNTERPARTY_AT_FAULT


SyncSettlementEvent = SyncSettlementApproved | SyncSettlementFailure


def parse_sync_settlement_event(item: dict[str, Any]) -> SyncSettlementEvent:
    """Parse one ``/sync/pending_settlements`` message (v0 payload or v1 envelope)."""
    channel = None
    if "data" in item and isinstance(item.get("data"), dict) and "channel" in item:
        channel = item.get("channel")
        item = item["data"]
    # v1 names the frame; v0 sends the bare payload, where only the failure carries a
    # reason (an approval carries the approval itself).
    if channel == "sync-settlement-failed" or (channel is None and "reason" in item):
        return SyncSettlementFailure.model_validate(item)
    return SyncSettlementApproved.model_validate(item)
