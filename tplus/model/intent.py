from decimal import Decimal

from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier


class IntentReport(BaseModel):
    """What a user is currently looking at, and how much of it they are contemplating.

    Replace, not accumulate: each report supersedes this user's previous one for
    the same asset, so revising 5 to 10 moves the aggregate by +5. Reporting
    ``watching=False`` with ``quantity=0`` withdraws entirely.

    Reports lapse after 60s server-side; re-report to stay counted.

    Not an order: nothing is matched, reserved, or margin-checked.
    """

    asset_id: AssetIdentifier
    watching: bool
    quantity: Decimal


class IntentAggregateUpdate(BaseModel):
    """One asset's aggregate movement over a 100ms window, as market makers see it.

    Carries no user identity by design — the aggregate is what makes the feed
    safe to publish. ``*_delta`` is the signed movement within the window;
    ``watchers``/``quantity`` are the totals once it is applied, which is what
    lets a market maker joining mid-session get absolute state without a
    snapshot.
    """

    asset_id: AssetIdentifier
    watchers_delta: int
    quantity_delta: Decimal
    watchers: int
    quantity: Decimal
    window_end_ns: int


def parse_intent_aggregate_update(data: dict) -> IntentAggregateUpdate:
    return IntentAggregateUpdate.model_validate(data)
