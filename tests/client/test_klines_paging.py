"""`iter_klines` walks past the cutoff a clamped kline read comes back with."""

from typing import Any

import pytest

from tplus.client import MarketDataClient
from tplus.model.asset_identifier import AssetIdentifier

ASSET = AssetIdentifier("200")
HOUR_NS = 3_600 * 1_000_000_000


def _bar(open_ns: int) -> dict[str, Any]:
    return {
        "open": "1",
        "high": "1",
        "low": "1",
        "close": "1",
        "volume": "1",
        "open_timestamp_ns": open_ns,
        "close_timestamp_ns": open_ns + HOUR_NS,
    }


def _page(opens: list[int], has_next: bool, truncated: int | None = None) -> dict[str, Any]:
    page: dict[str, Any] = {
        "items": [_bar(open_ns) for open_ns in opens],
        "page": 0,
        "limit": 2,
        "total_pages": 1,
        "cursor_size": len(opens),
        "has_next_page": has_next,
    }
    if truncated is not None:
        page["truncated_before_ns"] = truncated

    return page


@pytest.mark.anyio
async def test_iter_klines_follows_the_truncation_cutoff(monkeypatch: pytest.MonkeyPatch):
    client = MarketDataClient(base_url="http://127.0.0.1:8011")
    # A window too wide to read whole is served newest-first in two clamped reads.
    responses = [
        _page([4 * HOUR_NS, 3 * HOUR_NS], has_next=False, truncated=3 * HOUR_NS),
        _page([2 * HOUR_NS, 1 * HOUR_NS], has_next=False),
    ]
    ends: list[int] = []

    async def fake_get(endpoint: str, **kwargs: Any) -> Any:
        ends.append(kwargs["params"]["end_timestamp_ns"])
        return responses[len(ends) - 1]

    monkeypatch.setattr(client, "_get", fake_get)
    bars = [bar async for bar in client.iter_klines(ASSET, end_timestamp_ns=5 * HOUR_NS)]

    assert [bar.open_timestamp_ns for bar in bars] == [
        4 * HOUR_NS,
        3 * HOUR_NS,
        2 * HOUR_NS,
        1 * HOUR_NS,
    ], "the bars below the cutoff are reached rather than dropped"
    assert ends == [5 * HOUR_NS, 3 * HOUR_NS - 1], "the second read re-pins the end at the cutoff"


@pytest.mark.anyio
async def test_iter_klines_stops_when_the_read_was_not_clamped(monkeypatch: pytest.MonkeyPatch):
    client = MarketDataClient(base_url="http://127.0.0.1:8011")
    reads = 0

    async def fake_get(endpoint: str, **kwargs: Any) -> Any:
        nonlocal reads
        reads += 1
        return _page([1 * HOUR_NS], has_next=False)

    monkeypatch.setattr(client, "_get", fake_get)
    bars = [bar async for bar in client.iter_klines(ASSET, end_timestamp_ns=5 * HOUR_NS)]

    assert len(bars) == 1
    assert reads == 1, "a whole window is not re-read"


@pytest.mark.anyio
async def test_iter_klines_caps_reads_at_max_pages(monkeypatch: pytest.MonkeyPatch):
    client = MarketDataClient(base_url="http://127.0.0.1:8011")
    reads = 0

    async def fake_get(endpoint: str, **kwargs: Any) -> Any:
        nonlocal reads
        reads += 1
        # Always clamped, so only max_pages bounds the walk.
        end = kwargs["params"]["end_timestamp_ns"]
        return _page([end], has_next=False, truncated=end)

    monkeypatch.setattr(client, "_get", fake_get)
    bars = [
        bar async for bar in client.iter_klines(ASSET, end_timestamp_ns=5 * HOUR_NS, max_pages=3)
    ]

    assert reads == 3, "max_pages bounds the reads taken"
    assert len(bars) == 3
