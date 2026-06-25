import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class KlineUpdate(BaseModel):
    """Represents a single K-line (candlestick) update from the WebSocket stream."""

    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    open_timestamp_ns: int
    close_timestamp_ns: int

    @property
    def open_datetime(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(
            self.open_timestamp_ns / 1_000_000_000,
            tz=datetime.timezone.utc,
        )

    @property
    def close_datetime(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(
            self.close_timestamp_ns / 1_000_000_000,
            tz=datetime.timezone.utc,
        )


class KlinesPage(BaseModel):
    """One page of klines plus pagination metadata (the `Page<Timebar>` envelope)."""

    items: list[KlineUpdate]
    page: int
    limit: int
    total_pages: int
    cursor_size: int
    has_next_page: bool
    next_page: int | None = None


def parse_kline_update(data: list[dict[str, Any]]) -> list[KlineUpdate]:
    """Parses  a list of kline dictionaries into a List of KlineUpdate object."""
    try:
        return [
            KlineUpdate(
                open=Decimal(item["open"]),
                high=Decimal(item["high"]),
                low=Decimal(item["low"]),
                close=Decimal(item["close"]),
                volume=Decimal(item["volume"]),
                open_timestamp_ns=int(item["open_timestamp_ns"]),
                close_timestamp_ns=int(item["close_timestamp_ns"]),
            )
            for item in data
        ]
    except (KeyError, ValueError, TypeError) as e:
        print(f"Error parsing KlineUpdate: {e}. Data: {data}")
        raise ValueError(f"Invalid KlineUpdate data received: {data}") from e


def parse_klines_page(data: dict[str, Any] | list[dict[str, Any]]) -> KlinesPage:
    """Parse the `/klines` page envelope, tolerating a bare list from older servers."""
    if isinstance(data, list):
        items = parse_kline_update(data)
        count = len(items)
        return KlinesPage(
            items=items,
            page=0,
            limit=count,
            total_pages=1 if count else 0,
            cursor_size=count,
            has_next_page=False,
        )

    return KlinesPage(
        items=parse_kline_update(data.get("items", [])),
        page=int(data.get("page", 0)),
        limit=int(data.get("limit", 0)),
        total_pages=int(data.get("total_pages", 0)),
        cursor_size=int(data.get("cursor_size", 0)),
        has_next_page=bool(data.get("has_next_page", False)),
        next_page=data.get("next_page"),
    )
