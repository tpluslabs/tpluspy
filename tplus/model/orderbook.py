from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class OrderBook:
    def __init__(self,
                 asks: list[list[int]] = None,
                 bids: list[list[int]] = None,
                 sequence_number: int = 0):
        self.asks = asks or []  # List of [price, quantity]
        self.bids = bids or []  # List of [price, quantity]
        self.sequence_number = sequence_number

# Added for WebSocket Depth Stream
@dataclass
class PriceLevelUpdate:
    asset_id: int
    side: Literal["Ask", "Bid"]
    price_level: int # Assuming price is an integer
    quantity: int    # New quantity at this level (0 means level removed)

def parse_price_level_update(data: dict[str, Any]) -> PriceLevelUpdate:
    """Parses a dictionary into a PriceLevelUpdate object."""
    # Basic validation could be added here (e.g., check types, keys)
    try:
        return PriceLevelUpdate(
            asset_id=int(data['asset_id']),
            side=data['side'], # Assuming 'Ask' or 'Bid'
            price_level=int(data['price_level']),
            quantity=int(data['quantity'])
        )
    except (KeyError, ValueError, TypeError) as e:
        # Log the error and the problematic data
        # Consider raising a custom parsing error
        print(f"Error parsing PriceLevelUpdate: {e}. Data: {data}")
        raise ValueError(f"Invalid PriceLevelUpdate data received: {data}") from e
