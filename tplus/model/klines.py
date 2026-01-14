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


def parse_kline_update(data: list[dict[str, Any]]) -> List[KlineUpdate]:
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
