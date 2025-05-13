from typing import Any, Literal

from pydantic import BaseModel


class OrderBook(BaseModel):
    asks: list[list[float]] = []  # List of [price, quantity]
    bids: list[list[float]] = []  # List of [price, quantity]
    sequence_number: int = 0


# Model for WebSocket Depth Stream Diff updates
class OrderBookDiff(BaseModel):
    bids: list[list[float]]
    asks: list[list[float]]
    sequence_number: int


# Model for individual Price Level Updates (Potentially for a different stream?)
class PriceLevelUpdate(BaseModel):
    asset_id: int
    side: Literal["Ask", "Bid"]
    price_level: float  # Assuming price is an integer
    quantity: float  # New quantity at this level (0 means level removed)


def parse_price_level_update(data: dict[str, Any]) -> PriceLevelUpdate:
    """Parses a dictionary into a PriceLevelUpdate object."""
    # Basic validation could be added here (e.g., check types, keys)
    try:
        return PriceLevelUpdate(
            asset_id=int(data["asset_id"]),
            side=data["side"],  # Assuming 'Ask' or 'Bid'
            price_level=int(data["price_level"]),
            quantity=int(data["quantity"]),
        )
    except (KeyError, ValueError, TypeError) as e:
        # Log the error and the problematic data
        # Consider raising a custom parsing error
        print(f"Error parsing PriceLevelUpdate: {e}. Data: {data}")
        raise ValueError(f"Invalid PriceLevelUpdate data received: {data}") from e
