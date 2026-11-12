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


class ControlOrderResponse(BaseModel):
    """One per-order response off the ``/control`` channel, such as a ``CancelOrderResponse``.

    ``message`` is the response variant as the OMS names it, so a caller can tell a
    cancel response from any other order response on the same connection.
    """

    message: str
    order_id: str
    status: str
    reason: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ControlOrderResponse | None":
        """Read ``{variant: {"response": {...}}}``; ``None`` for any other shape."""
        if not isinstance(payload, dict) or len(payload) != 1:
            return None
        message, content = next(iter(payload.items()))
        response = content.get("response") if isinstance(content, dict) else None
        if not isinstance(response, dict) or "order_id" not in response:
            return None
        return cls(
            message=str(message),
            order_id=str(response["order_id"]),
            status=str(response.get("status")),
            reason=response.get("reason"),
        )
