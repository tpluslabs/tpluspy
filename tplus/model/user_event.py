"""Typed user-activity events emitted by the OMS on `/account/events/{user_id}`.

Each variant is a separate model. The wire JSON looks like a tagged enum:
`{"DepositLanded": { ... }}` or `{"WithdrawalCompleted": { ... }}`.

Use `parse_user_event(item)` to dispatch into the right model.

Note: liquidation fills are surfaced via the `is_liquidation` flag on
`UserTrade` / `Trade` (on the trades streams) — not as a dedicated event
here, to avoid double-counting.
"""

from decimal import Decimal
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


class SettlementCompleted(BaseModel):
    """An on-chain settlement has been ingested into the user's sub-account.

    Any settlement, sync or not: `amount_out` of `asset_out` left the
    sub-account and `amount_in` of `asset_in` came in, both in
    `INVENTORY_DECIMALS` (1e18) as base-10 strings.
    """

    model_config = ConfigDict(populate_by_name=True)

    user: str
    sub_account_index: int
    settler: str
    mode: str
    asset_in: str
    amount_in: str
    asset_out: str
    amount_out: str
    chain_id: str
    settlement_nonce: int
    timestamp_ns: int


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

    `amount` is in `INVENTORY_DECIMALS` (1e18), encoded as a base-10 string.
    """

    model_config = ConfigDict(populate_by_name=True)

    user: str
    source_sub_account_index: int
    target_sub_account_index: int
    asset: str
    amount: str
    timestamp_ns: int


class CalledVenue(BaseModel):
    """One called venue and the moment its own offsets lapse.

    Deadlines are per venue: each venue's grace period comes from its own
    `margin_call_timeout_ns` in the netting table, and a venue called later
    than another keeps its own later deadline while the first keeps its
    original. There is no account-level deadline — take `min` over these if you
    want a single "act by".
    """

    model_config = ConfigDict(populate_by_name=True)

    venue: int
    deadline_ns: int


class MarginCallUpdated(BaseModel):
    """A sub-account's margin-call state changed.

    Emitted when the clearing engine opens, keeps, or clears a margin call:
    `called_venues` lists the called venues with their own deadlines, and is
    empty when the call cleared. See the `margin_calls` field on the margin
    endpoint for the current state; this event is the notification that it
    moved.
    """

    model_config = ConfigDict(populate_by_name=True)

    user: str
    sub_account_index: int
    called_venues: list[CalledVenue] = []
    timestamp_ns: int


class InterestPayment(BaseModel):
    """One market's interest flows on one sub-account for an epoch.

    Amounts are USD decimals: negative when the account paid, positive when it
    earned. Each rate is the market's rate for the epoch that its amount comes
    from, as a fraction (`0.0001` is 0.01%); the funding rate is positive when
    longs pay shorts, negative when shorts pay longs.
    """

    model_config = ConfigDict(populate_by_name=True)

    funding_amount: Decimal
    utilization_amount: Decimal
    quote_utilization_amount: Decimal
    funding_rate: Decimal
    utilization_rate: Decimal
    quote_utilization_rate: Decimal


class InterestEpochOccurred(BaseModel):
    """The clearing engine applied an interest epoch that moved this user's balances.

    `payments` is keyed by market asset identifier, then by sub-account index;
    only sub-accounts the epoch touched appear. Accounts the epoch left alone
    get no event.
    """

    model_config = ConfigDict(populate_by_name=True)

    user: str
    payments: dict[str, dict[int, InterestPayment]]
    timestamp_ns: int


UserActivityEvent = (
    DepositLanded
    | WithdrawalCompleted
    | SettlementCompleted
    | PositionCleared
    | SubAccountAssetTransferred
    | MarginCallUpdated
    | InterestEpochOccurred
)


_VARIANTS: dict[str, type[BaseModel]] = {
    "DepositLanded": DepositLanded,
    "WithdrawalCompleted": WithdrawalCompleted,
    "SettlementCompleted": SettlementCompleted,
    "PositionCleared": PositionCleared,
    "SubAccountAssetTransferred": SubAccountAssetTransferred,
    "MarginCallUpdated": MarginCallUpdated,
    "InterestEpochOccurred": InterestEpochOccurred,
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
