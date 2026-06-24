import time

from tplus.client.base import BaseClient
from tplus.utils.operator import load_operator_sk, sign_operator_payload


class BlockchainClient(BaseClient):
    """Admin HTTP client for a blockchain client (threshold / anvil).

    Authenticates with a secp256k1 operator signature rather than Ed25519 user signing.
    ``base_url`` points at the blockchain client's health-API port.
    """

    async def sync_vault_events(
        self,
        from_block: int,
        to_block: int,
        *,
        address: str | None = None,
        events: list[str] | None = None,
        operator_secret: str | None = None,
        timestamp_ms: int | None = None,
    ) -> None:
        """Trigger re-ingestion of on-chain events in ``[from_block, to_block]``.

        Fire-and-forget: the client re-queries logs and replays them over the overlay, so nothing
        is returned here. Pass ``operator_secret`` for authenticated (threshold) clients; omit it
        for anvil.
        """
        timestamp = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
        events_str = ",".join(events) if events else ""
        payload = f"{from_block}:{to_block}:{timestamp}:{address or ''}:{events_str}".encode()

        signature = ""
        if operator_secret is not None:
            signature = sign_operator_payload(payload, load_operator_sk(operator_secret))

        body: dict = {
            "from_block": from_block,
            "to_block": to_block,
            "timestamp": timestamp,
            "signature": signature,
        }
        if address is not None:
            body["address"] = address
        if events is not None:
            body["events"] = events

        # "historical_logs" is the blockchain client's existing route name.
        await self._post("historical_logs", json_data=body, requires_auth=False)
