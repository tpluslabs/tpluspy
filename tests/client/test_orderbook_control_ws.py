import asyncio
import json
from typing import Any

import pytest


class DummyWS:
    def __init__(self):
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self.sent: list[str] = []
        self.closed = False

    async def send(self, data: str) -> None:
        self.sent.append(data)

    def feed(self, data: dict[str, Any]) -> None:
        self._queue.put_nowait(json.dumps(data))

    def __aiter__(self):
        return self

    async def __anext__(self):
        # Block until a message is fed; reader task will be cancelled by client.close()
        return await self._queue.get()

    async def close(self):
        self.closed = True


@pytest.mark.anyio
async def test_pending_key_composite(monkeypatch, anyio_backend):
    if anyio_backend != "asyncio":
        pytest.skip("OrderBookClient control channel uses asyncio internals")
    from typing import Any, cast

    from tplus.client.orderbook import OrderBookClient

    class DummyClient(OrderBookClient):
        async def _ensure_control_ws(self) -> None:
            if not self._control_ws:
                # Help type-checker: treat DummyWS as Any when assigning to _control_ws
                self._control_ws = cast(Any, DummyWS())
                # Start reader loop like the real client does
                self._control_ws_task = asyncio.create_task(self._control_ws_reader())

    class DummyUser:
        public_key = "USER"

    client = DummyClient(
        "http://example.com",
        default_user=DummyUser(),  # type: ignore
    )
    client._use_ws_control = True

    order_id = "abc"
    payload = {"CancelOrderRequest": {"cancel": {"order_id": order_id, "asset_id": "200"}}}

    # Ensure control connection is established before sending
    await client._ensure_control_ws()
    ws = client._control_ws  # type: ignore[assignment]
    assert ws is not None

    fut_task = asyncio.create_task(
        client._control_ws_send(payload, expected_order_id=order_id, timeout=0.5)
    )
    # Yield to event loop to allow registration of the pending future
    await asyncio.sleep(0)

    # Response comes back
    ws.feed(  # type: ignore[attr-defined]
        {
            "CancelOrderResponse": {
                "response": {"order_id": order_id, "status": "Received"},
                "asset_id": "200",
            }
        }
    )

    res = await fut_task
    assert isinstance(res, dict)
    assert "CancelOrderResponse" in res

    # Cleanup
    await client.close()


@pytest.mark.anyio
async def test_batch_create_over_control_ws(monkeypatch, anyio_backend):
    if anyio_backend != "asyncio":
        pytest.skip("OrderBookClient control channel uses asyncio internals")
    from typing import Any, cast

    from tplus.client.orderbook import OrderBookClient

    class DummyClient(OrderBookClient):
        async def _ensure_control_ws(self) -> None:
            if not self._control_ws:
                self._control_ws = cast(Any, DummyWS())
                self._control_ws_task = asyncio.create_task(self._control_ws_reader())

    class DummyUser:
        public_key = "USER"

    client = DummyClient("http://example.com", default_user=DummyUser())  # type: ignore
    client._use_ws_control = True

    # Stand in for a BatchCreateOrderRequest: only model_dump() is exercised by the
    # control-ws batch path.
    class FakeBatch:
        def model_dump(self):
            return {
                "orders": [
                    {"order": {"order_id": "oid1", "base_asset": "200"}, "signature": [1]},
                    {"order": {"order_id": "oid2", "base_asset": "200"}, "signature": [1]},
                ]
            }

    await client._ensure_control_ws()
    ws = client._control_ws
    assert ws is not None

    task = asyncio.create_task(
        client._control_ws_send_batch(FakeBatch(), timeout=1.0)  # type: ignore[arg-type]
    )
    await asyncio.sleep(0)

    # Server acks once (no order id → ignored), then streams one response per order,
    # out of submission order, mixing acceptance and a per-order rejection.
    ws.feed({"request": {"status": "submitted"}})  # type: ignore[attr-defined]
    ws.feed(  # type: ignore[attr-defined]
        {
            "CreateOrderResponse": {
                "response": {
                    "order_id": "oid2",
                    "status": "Rejected",
                    "reason": "InsufficientInventory",
                },
                "asset_id": "200",
            }
        }
    )
    ws.feed(  # type: ignore[attr-defined]
        {
            "CreateOrderResponse": {
                "response": {"order_id": "oid1", "status": "Received", "reason": None},
                "asset_id": "200",
            }
        }
    )

    resp = await task

    # One BatchCreateRequest frame was sent.
    sent = json.loads(ws.sent[0])  # type: ignore[attr-defined]
    assert list(sent.keys()) == ["BatchCreateRequest"]

    by_id = {s.order_id: s for s in resp.batch_order_status}
    assert by_id["oid1"].status == "Received"
    assert by_id["oid1"].reason is None
    assert by_id["oid2"].status == "Rejected"
    assert by_id["oid2"].reason == "InsufficientInventory"

    await client.close()
