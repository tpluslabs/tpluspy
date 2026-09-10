import time
from typing import TYPE_CHECKING

from tplus.client.clearingengine.base import BaseClearingEngineClient

if TYPE_CHECKING:
    from tplus.types import UserLike


class CrossVenueClient(BaseClearingEngineClient):
    """User-facing cross-venue (e.g. Hyperliquid) margin APIs on the clearing engine."""

    async def get_venue_state(self, user: "UserLike", venue: int) -> dict:
        """Read the caller's cross-venue ``(user, venue)`` state.

        User-authenticated: the query is signed with ``user``'s key, so a user
        can only read their own venue state. Returns
        ``{venue_present, allocation_bps, assigned_to, locked, usd_balance,
        limit}`` — ``venue_present`` flips true once the adapter binding reaches
        the CE, ``allocation_bps`` is non-zero once the credit line is applied,
        and ``assigned_to`` is its sub-account index under ``user`` (or ``None``
        before a credit line exists).

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
        return await self._get(endpoint, requires_auth=False)
