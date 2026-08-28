import asyncio
import json
from typing import Any

import pytest

from tplus.client import BlockchainClient
from tplus.client.orderbook import OrderBookClient
from tplus.utils.user import User


class ControlWS:
    """Stands in for the `/control` websocket: records sends, replays fed frames."""

    def __init__(self) -> None:
        self._inbound: asyncio.Queue[str] = asyncio.Queue()
        self.sent: list[str] = []
        self.closed = False

    async def send(self, data: str) -> None:
        self.sent.append(data)

    def feed(self, frame: dict[str, Any]) -> None:
        self._inbound.put_nowait(json.dumps(frame))

    def sent_frame(self, index: int = 0) -> dict[str, Any]:
        return json.loads(self.sent[index])

    def __aiter__(self) -> "ControlWS":
        return self

    async def __anext__(self) -> str:
        return await self._inbound.get()

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def blockchain_client(mocker):
    """A BlockchainClient with its HTTP ``_post`` mocked out."""
    client = BlockchainClient(base_url="http://127.0.0.1:8080")
    mocker.patch.object(client, "_post", new=mocker.AsyncMock(return_value={}))
    return client


@pytest.fixture
def control_ws() -> ControlWS:
    return ControlWS()


@pytest.fixture
def control_user() -> User:
    return User()


@pytest.fixture
async def control_ws_client(mocker, control_ws, control_user, anyio_backend):
    """An ``OrderBookClient`` whose `/control` websocket is :func:`control_ws`."""
    if anyio_backend != "asyncio":
        pytest.skip("OrderBookClient control channel uses asyncio internals")

    connection = mocker.AsyncMock()
    connection.__aenter__.return_value = control_ws
    client = OrderBookClient("http://example.com", default_user=control_user, use_ws_control=True)
    mocker.patch.object(client, "_open_ws", new=mocker.AsyncMock(return_value=connection))
    yield client
    await client.close()
