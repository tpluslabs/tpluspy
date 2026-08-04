import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel


class Interval(str, Enum):
    """Kline bucket width, mirroring `orderbook_messages::interval::Interval`.

    Values are the canonical spellings the server round-trips; it also accepts the
    suffixed forms (`5m`, `4h`, `1d`) on the wire. Only `1M` is case-sensitive: it is a
    month, while `1m` is a minute.
    """

    SEC_1 = "1S"
    SEC_5 = "5S"
    SEC_15 = "15S"
    SEC_30 = "30S"
    MIN_1 = "1"
    MIN_3 = "3"
    MIN_5 = "5"
    MIN_15 = "15"
    MIN_30 = "30"
    HOUR_1 = "60"
    HOUR_2 = "120"
    HOUR_4 = "240"
    HOUR_6 = "360"
    HOUR_8 = "480"
    HOUR_12 = "720"
    DAY_1 = "1D"
    DAY_3 = "3D"
    WEEK_1 = "1W"
    MONTH_1 = "1M"

    def __str__(self) -> str:
        return self.value


class Timebar(BaseModel):
    """One candlestick, mirroring `orderbook_messages::market_data::Timebar`."""

    open: Decimal
    close: Decimal
    low: Decimal
    high: Decimal
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

    items: list[Timebar]
    page: int
    limit: int
    total_pages: int
    cursor_size: int
    has_next_page: bool
    next_page: int | None = None


def parse_timebars(data: list[dict[str, Any]]) -> list[Timebar]:
    """Parses a list of kline dictionaries into Timebar objects."""
    try:
        return [
            Timebar(
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
        print(f"Error parsing Timebar: {e}. Data: {data}")
        raise ValueError(f"Invalid Timebar data received: {data}") from e


def parse_klines_page(data: dict[str, Any] | list[dict[str, Any]]) -> KlinesPage:
    """Parse the `/klines` page envelope, tolerating a bare list from older servers."""
    if isinstance(data, list):
        items = parse_timebars(data)
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
        items=parse_timebars(data.get("items", [])),
        page=int(data.get("page", 0)),
        limit=int(data.get("limit", 0)),
        total_pages=int(data.get("total_pages", 0)),
        cursor_size=int(data.get("cursor_size", 0)),
        has_next_page=bool(data.get("has_next_page", False)),
        next_page=data.get("next_page"),
    )
