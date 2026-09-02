from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest

from tplus.client.orderbook import OrderBookClient
from tplus.model.position import PositionUpdate
from tplus.utils.user import User


@pytest.mark.anyio
async def test_stream_user_positions_uses_authenticated_user_route(mocker):
    account = User()
    client = OrderBookClient("http://example.com", default_user=account)
    frame = {
        "user_id": account.public_key,
        "positions": [],
        "timestamp_ns": 123,
    }

    async def stream_ws(
        path: str,
        parser: Callable[[Any], Any],
        *,
        user: Any = None,
        **_: Any,
    ) -> AsyncIterator[PositionUpdate]:
        assert path == f"/positions/ws/{account.public_key}"
        assert user is None
        yield parser(frame)

    mocker.patch.object(client, "_stream_ws", new=stream_ws)

    updates = [update async for update in client.stream_user_positions()]

    assert len(updates) == 1
    assert updates[0].user_id == account.public_key
    assert updates[0].timestamp_ns == 123
    await client.close()
