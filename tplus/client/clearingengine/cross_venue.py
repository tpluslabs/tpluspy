import time
from typing import TYPE_CHECKING

from tplus.client.clearingengine.base import BaseClearingEngineClient

if TYPE_CHECKING:
    from tplus.utils.user import User


class CrossVenueClient(BaseClearingEngineClient):
    """User-facing cross-venue (e.g. Hyperliquid) margin APIs on the clearing engine."""

    async def get_venue_state(self, user: "User", venue: int) -> dict:
        """Read the caller's cross-venue ``(user, venue)`` state.

        User-authenticated: the query is signed with ``user``'s key, so a user
        can only read their own venue state. Returns
        ``{venue_present, allocation_bps, locked, usd_balance}`` — ``venue_present``
        flips true once the adapter binding reaches the CE, and ``allocation_bps``
        is non-zero once the credit line is applied.
        """
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
