from typing import Any

from eth_pydantic_types import HexBytes
from pydantic import BaseModel, field_validator

from tplus.model.conversion import ConversionInfo


class InnerApproval(BaseModel):
    nonce: int
    signature: HexBytes


class SettlementApproval(BaseModel):
    inner: InnerApproval
    expiry: int

    amount_in: int
    """The chain amount the vault takes in."""

    amount_out: int
    """The chain amount the vault sends out."""

    conversion: ConversionInfo
    """What the token-out leg became under the rate this approval was signed at."""

    reserved_fee: int | None = None
    """The rebalancing fee the settlement holds off the lock owner's balance until its
    payout, in canonical units of the outgoing asset at 1e18; the payout collects at most
    this and returns the rest. ``None`` when it reserved nothing."""


class WithdrawalApproval(BaseModel):
    inner: InnerApproval
    expiry: int

    epoch_hash: HexBytes
    """The checkpoint epoch hash the approval is tied to."""

    amount: int
    """The chain amount the vault pays out."""

    conversion: ConversionInfo
    """What the debited canonical amount became under the rate this approval was signed at."""

    @field_validator("epoch_hash", mode="before")
    @classmethod
    def validate_epoch_hash(cls, value: Any) -> Any:
        # The clearing engine serializes the hash as a list of 32 byte values.
        if isinstance(value, list):
            return bytes(value)

        return value
