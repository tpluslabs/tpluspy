from typing import Any, Literal, Union

from pydantic import BaseModel, Field

from tplus.model.asset_identifier import IndexAsset


class Trade(BaseModel):
    asset_id: IndexAsset
    trade_id: int
    order_id: str
    price: float
    quantity: int
    timestamp_ns: int
    is_maker: bool
    is_buyer: bool
    confirmed: bool


def parse_trades(data: list[dict]) -> list[Trade]:
    return [
        Trade(
            asset_id=IndexAsset(**item["asset_id"]),
            trade_id=item["trade_id"],
            order_id=item["order_id"],
            price=item["price"],
            quantity=item["quantity"],
            timestamp_ns=item["timestamp_ns"],
            is_maker=item["is_maker"],
            is_buyer=item["is_buyer"],
            confirmed=item["confirmed"],
        )
        for item in data
    ]


# --- WebSocket Trade Events ---


class BaseTradeEvent(BaseModel):
    event_type: str


class TradePendingEvent(BaseTradeEvent):
    """Represents a trade that has occurred but is awaiting final confirmation."""

    event_type: Literal["PENDING"] = Field(default="PENDING")
    # Include fields available at the pending stage
    order_id: str
    match_id: str  # Or some identifier for the match
    price: float
    quantity: int
    timestamp_ns: int
    # Maybe asset_id, buyer/seller info if available


class TradeConfirmedEvent(BaseTradeEvent):
    """Represents a finalized trade."""

    event_type: Literal["CONFIRMED"] = Field(default="CONFIRMED")
    trade: Trade  # The fully confirmed trade details


# Union type for type hinting
TradeEvent = Union[TradePendingEvent, TradeConfirmedEvent]


# Helper to parse a single trade dict (similar to parse_trades but for one)
def parse_single_trade(item: dict[str, Any]) -> Trade:
    """Parses a single trade dictionary into a Trade object."""
    try:
        return Trade(
            asset_id=IndexAsset(**item["asset_id"]),
            trade_id=item["trade_id"],
            order_id=item["order_id"],
            price=float(item["price"]),
            quantity=int(item["quantity"]),
            timestamp_ns=int(item["timestamp_ns"]),
            is_maker=bool(item["is_maker"]),
            is_buyer=bool(item["is_buyer"]),
            confirmed=bool(item["confirmed"]),
        )
    except (KeyError, ValueError, TypeError) as e:
        # Add logging if desired
        raise ValueError(f"Invalid single trade data: {item}") from e


def parse_trade_event(data: dict[str, Any]) -> TradeEvent:
    """Parses a trade event dictionary from the WebSocket stream."""
    event_type = data.get("event_type")
    payload = data.get("payload", {})

    if not event_type or not isinstance(payload, dict):
        raise ValueError(f"Invalid trade event structure: {data}")

    try:
        if event_type == "PENDING":
            # Assuming payload directly contains the fields for TradePendingEvent
            return TradePendingEvent(
                order_id=payload["order_id"],
                match_id=payload["match_id"],
                price=float(payload["price"]),
                quantity=int(payload["quantity"]),
                timestamp_ns=int(payload["timestamp_ns"]),
            )

        elif event_type == "CONFIRMED":
            # Assume payload is the raw trade dictionary
            parsed_trade = parse_single_trade(payload)
            return TradeConfirmedEvent(trade=parsed_trade)

        else:
            # Add logging
            raise ValueError(f"Unknown trade event type: {event_type}")

    except (KeyError, ValueError, TypeError) as e:
        # Add logging
        raise ValueError(f"Invalid data for trade event type {event_type}: {data}") from e
