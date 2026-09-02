import json
from typing import Any

from pydantic import BaseModel, ConfigDict

HEARTBEAT_TYPES = frozenset({"subscriptions", "ping", "pong"})


class ControlWSFrame(BaseModel):
    """A frame off the OMS `/control` WebSocket.

    Every field is optional so that pre-v1 frames, which arrive as a bare order
    response with no envelope around it, still parse.
    """

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    channel: str | None = None
    request_id: str | None = None
    data: Any = None
    error: dict[str, Any] | None = None

    @classmethod
    def parse(cls, message: str | bytes) -> "ControlWSFrame":
        raw = json.loads(message)
        if not isinstance(raw, dict):
            raise ValueError(f"Control WS frame is not an object: {raw!r}")

        return cls.model_validate(raw)

    @property
    def is_heartbeat(self) -> bool:
        return self.type in HEARTBEAT_TYPES

    @property
    def is_ack(self) -> bool:
        """Whether this is the non-terminal ``submitted`` ack that precedes the response."""
        if self.type == "ack":
            return True

        status = self.data.get("request") if isinstance(self.data, dict) else None
        return isinstance(status, dict) and status.get("status") == "submitted"

    @property
    def order_payload(self) -> dict[str, Any] | None:
        """The order-keyed body: the envelope's ``data``, or an unenveloped frame as-is."""
        payload = self.data if self.data is not None else self.model_extra
        return payload if isinstance(payload, dict) and payload else None
