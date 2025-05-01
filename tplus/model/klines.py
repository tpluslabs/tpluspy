import datetime
from dataclasses import dataclass
from typing import Any


@dataclass
class KlineUpdate:
    """Represents a single K-line (candlestick) update from the WebSocket stream."""
    asset_id: int
    timestamp: int # Unix timestamp (e.g., seconds or milliseconds)
    open: int
    high: int
    low: int
    close: int
    volume: int
    # Optional: Add interval if provided by the stream
    # interval: str

    @property
    def datetime(self) -> datetime.datetime:
        """Converts the timestamp to a Python datetime object (assuming seconds)."""
        # Adjust unit if the timestamp is in milliseconds (e.g., / 1000)
        return datetime.datetime.fromtimestamp(self.timestamp, tz=datetime.timezone.utc)

def parse_kline_update(data: dict[str, Any]) -> KlineUpdate:
    """Parses a dictionary into a KlineUpdate object."""
    try:
        # Assuming the keys match the dataclass fields directly
        # Perform necessary type conversions (e.g., int)
        return KlineUpdate(
            asset_id=int(data['asset_id']), # Assuming asset_id is part of the kline message
            timestamp=int(data['timestamp']),
            open=int(data['open']),
            high=int(data['high']),
            low=int(data['low']),
            close=int(data['close']),
            volume=int(data['volume'])
        )
    except (KeyError, ValueError, TypeError) as e:
        print(f"Error parsing KlineUpdate: {e}. Data: {data}")
        raise ValueError(f"Invalid KlineUpdate data received: {data}") from e
