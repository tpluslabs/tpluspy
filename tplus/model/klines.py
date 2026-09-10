import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel

from tplus.model.pagination import PageContinuation


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


class KlinesPage(PageContinuation):
    """One page of klines plus continuation metadata."""

    items: list[Timebar]
    truncated_before_ns: int | None = None


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
        return KlinesPage(items=items)

    return KlinesPage(
        items=parse_timebars(data.get("items", [])),
        has_next_page=bool(data.get("has_next_page", False)),
        next_page=data.get("next_page"),
        truncated_before_ns=data.get("truncated_before_ns"),
    )
