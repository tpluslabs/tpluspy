import time
from typing import TYPE_CHECKING, TypedDict, cast

from tplus.client.clearingengine.base import BaseClearingEngineClient

if TYPE_CHECKING:
    from tplus.types import UserLike


class XmVenueMarginPosition(TypedDict):
    """One canonical margin position; amounts are signed 1e18 decimal strings."""

    asset_balance: str
    quote_balance: str


class XmVenueBalance(TypedDict):
    """Latest canonical balance reported by the venue adapter."""

    spot: dict[str, str]
    margins: dict[str, XmVenueMarginPosition]
    timestamp_ms: int


class XmVenueState(TypedDict):
    """Authenticated CE view of one user's external-margin venue."""

    venue_present: bool
    allocation_bps: int
    assigned_to: int | None
    locked: bool
    usd_balance: str
    limit: str
    balance: XmVenueBalance | None


class CrossVenueClient(BaseClearingEngineClient):
    """User-facing external-venue margin APIs on the clearing engine."""

    async def get_venue_state(self, user: "UserLike", venue: int) -> XmVenueState:
        """Read the caller's cross-venue ``(user, venue)`` state.

        User-authenticated: the query is signed with ``user``'s key, so a user
        can only read their own venue state. Returns
        ``{venue_present, allocation_bps, assigned_to, locked, usd_balance,
        limit, balance}`` —
        ``venue_present`` flips true once the adapter binding reaches the CE,
        ``allocation_bps`` is non-zero once the credit line is applied, and
        ``assigned_to`` is its sub-account index under ``user`` (or ``None``
        before a credit line exists). ``balance`` is ``None`` only for an absent
        venue. Otherwise, it contains the latest canonical ``spot`` and
        ``margins`` maps keyed by canonical asset-identifier strings; monetary
        values are base-10 strings in 1e18 units. ``timestamp_ms`` is the source
        adapter's Unix-millisecond observation time. ``usd_balance`` is retained
        for compatibility and comes from the same latest balance.

        The response is the CE's canonical aggregate and does not contain raw
        venue-specific account-family breakdowns.

        ``limit`` is the operator cap this pair's margin is charged against, a
        base-10 string in 1e18 decimals. It is never absent: an unconfigured
        pair reports the default it will be created with, so the answer is
        always "what will margin charge against", not "has anyone set one".
        """
        user = self._resolve_user(user)
        ts = time.time_ns()
        sep = b"\x1f"
        # Must match `xm_venue_state_signing_payload` in the CE creditline route.
        payload = (
            b"xm_venue_state_query_v1"
            + sep
            + bytes.fromhex(user.public_key)
            + sep
            + venue.to_bytes(8, "big")
            + sep
            + ts.to_bytes(8, "big")
        )
        signature = user.sk.sign(payload).hex()
        endpoint = f"xm/venue/{user.public_key}/{venue}?timestamp_ns={ts}&signature={signature}"
        return cast(XmVenueState, await self._get(endpoint, requires_auth=False))
