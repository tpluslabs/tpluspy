"""Typed user-activity events emitted by the OMS on `/account/events/{user_id}`.

Each variant is a separate model. The wire JSON looks like a tagged enum:
`{"DepositLanded": { ... }}` or `{"WithdrawalCompleted": { ... }}`.

Use `parse_user_event(item)` to dispatch into the right model.

Note: liquidation fills are surfaced via the `is_liquidation` flag on
`UserTrade` / `Trade` (on the trades streams) — not as a dedicated event
here, to avoid double-counting.
"""

from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field


class DepositLanded(BaseModel):
    """An on-chain deposit has been ingested into the user's inventory."""

    model_config = ConfigDict(populate_by_name=True)

    user: str
    asset: str
    amount: str  # U256 in INVENTORY_DECIMALS (1e18) — string-encoded by serde
    chain_id: str = Field(alias="chain_id")
    deposit_nonce: int = Field(alias="deposit_nonce")
    timestamp_ns: int = Field(alias="timestamp_ns")


class WithdrawalCompleted(BaseModel):
    """An on-chain withdrawal has been ingested into the user's inventory."""

    model_config = ConfigDict(populate_by_name=True)

    user: str
    asset: str
    amount: str
    chain_id: str = Field(alias="chain_id")
    withdrawal_nonce: int = Field(alias="withdrawal_nonce")
    timestamp_ns: int = Field(alias="timestamp_ns")


class PositionCleared(BaseModel):
    """A margin position was cleared via the close-position flow.

    Realized PnL was moved to/from the spot balance and the position was
    removed from the sub-account. Distinct from "closing a position" by
    trading the base back to zero exposure.
    """

    model_config = ConfigDict(populate_by_name=True)

    user: str
    sub_account_index: int
    asset: str
    timestamp_ns: int


class SubAccountAssetTransferred(BaseModel):
    """The user transferred an asset between two of their own sub-accounts.

    `amount` is in `INVENTORY_DECIMALS` (1e18), encoded as 0x-hex.
    """

    model_config = ConfigDict(populate_by_name=True)

    user: str
    source_sub_account_index: int
    target_sub_account_index: int
    asset: str
    amount: str
    timestamp_ns: int


UserActivityEvent = (
    DepositLanded | WithdrawalCompleted | PositionCleared | SubAccountAssetTransferred
)


_VARIANTS: dict[str, type[BaseModel]] = {
    "DepositLanded": DepositLanded,
    "WithdrawalCompleted": WithdrawalCompleted,
    "PositionCleared": PositionCleared,
    "SubAccountAssetTransferred": SubAccountAssetTransferred,
}


def parse_user_event(item: dict[str, Any]) -> UserActivityEvent:
    """Dispatch a `UserActivityEvent` JSON object into the right model.

    Wire shape: `{"DepositLanded": {...}}` (serde-default tagged-enum form).
    Returns the inner model. Raises ValueError on unknown / malformed input.
    """
    if not isinstance(item, dict) or len(item) != 1:
        raise ValueError(f"Invalid user activity event: {item!r}")
    (variant, payload) = next(iter(item.items()))
    cls = _VARIANTS.get(variant)
    if cls is None:
        raise ValueError(f"Unknown user activity event variant: {variant!r}")
    return cast(UserActivityEvent, cls.model_validate(payload))
