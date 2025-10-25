from typing import Any, Literal

from pydantic import BaseModel, Field

from tplus.model.asset_identifier import AssetIdentifier


class Trade(BaseModel):
    asset_id: AssetIdentifier
    trade_id: int
    order_id: str = ""  # Optional for basic trades
    price: float  # Stored as float for convenience, comes as string from API
    quantity: float
    timestamp_ns: int
    buyer_is_maker: bool = Field(..., description="True if the buyer was the maker")
    status: Literal["Pending", "Confirmed", "Rollbacked"] = "Confirmed"


class UserTrade(BaseModel):
    """User-specific trade data with comprehensive order and execution details."""

    asset_id: AssetIdentifier
    trade_id: int
    order_id: str
    price: float  # Stored as float for convenience, comes as string from API
    quantity: float
    timestamp_ns: int
    is_maker: bool = Field(..., description="True if this user was the maker")
    is_buyer: bool = Field(..., description="True if this user was the buyer")
    status: Literal["Pending", "Confirmed", "Rollbacked"]

    @property
    def buyer_is_maker(self) -> bool:
        """Derived field for compatibility - True if buyer was maker."""
        return self.is_buyer and self.is_maker


def parse_trades(data: list[dict]) -> list[Trade]:
    return [
        Trade(
            asset_id=AssetIdentifier(item["asset_id"]),
            trade_id=item["trade_id"],
            order_id=item.get("order_id", ""),
            price=float(item["price"]),
            quantity=float(item["quantity"]),
            timestamp_ns=int(item["timestamp_ns"]),
            buyer_is_maker=item.get("buyer_is_maker", item.get("is_maker", False)),
            status=item.get("status", "Confirmed"),
        )
        for item in data
    ]


def parse_user_trades(data: list[dict]) -> list[UserTrade]:
    """Parse user trade data into UserTrade objects."""
    return [UserTrade.model_validate(item) for item in data]


class BaseTradeEvent(BaseModel):
    event_type: str


class TradePendingEvent(BaseTradeEvent):
    """Represents a trade that has occurred but is awaiting final confirmation."""

    event_type: Literal["Pending"] = Field(default="Pending")
    trade: Trade


class TradeConfirmedEvent(BaseTradeEvent):
    """Represents a finalized trade."""

    event_type: Literal["Confirmed"] = Field(default="Confirmed")
    trade: Trade


class TradeRollbackedEvent(BaseTradeEvent):
    """Represents a finalized trade."""

    event_type: Literal["Rollbacked"] = Field(default="Rollbacked")
    trade: Trade


TradeEvent = TradePendingEvent | TradeConfirmedEvent | TradeRollbackedEvent


def parse_single_trade(item: dict[str, Any]) -> Trade:
    """Parses a single trade dictionary into a Trade object."""
    try:
        return Trade(
            asset_id=AssetIdentifier(item["asset_id"]),
            trade_id=item["trade_id"],
            order_id=item.get("order_id", ""),
            price=float(item["price"]),
            quantity=float(item["quantity"]),
            timestamp_ns=int(item["timestamp_ns"]),
            buyer_is_maker=bool(item.get("buyer_is_maker", item.get("is_maker", False))),
            status=item.get("status", "Confirmed"),
        )
    except (KeyError, ValueError, TypeError) as e:
        raise ValueError(f"Invalid single trade data: {item}") from e


def parse_single_user_trade(item: dict[str, Any]) -> UserTrade:
    """Parses a single user trade dictionary into a UserTrade object."""
    try:
        return UserTrade(
            asset_id=AssetIdentifier(item["asset_id"]),
            trade_id=item["trade_id"],
            order_id=item["order_id"],
            price=float(item["price"]),
            quantity=float(item["quantity"]),
            timestamp_ns=int(item["timestamp_ns"]),
            is_maker=bool(item["is_maker"]),
            is_buyer=bool(item["is_buyer"]),
            status=item["status"],
        )
    except (KeyError, ValueError, TypeError) as e:
        raise ValueError(f"Invalid user trade data: {item}") from e


def parse_trade_event(data: dict[str, Any]) -> TradeEvent:
    """Parses a trade event dictionary from the WebSocket stream."""
    if not data:
        raise ValueError("Empty trade event")

    event_type = list(data.keys())[0]
    if not event_type or event_type not in ["Confirmed", "Pending", "Rollbacked"]:
        raise ValueError(f"Invalid trade event structure: {data}")

    if not (payload := data.get(event_type)):
        raise ValueError("Payload not present")

    try:
        parsed_trade = parse_single_trade(payload)
        if event_type == "Pending":
            return TradePendingEvent(trade=parsed_trade)
        elif event_type == "Confirmed":
            return TradeConfirmedEvent(trade=parsed_trade)

        # No other option, already validated above.
        return TradeRollbackedEvent(trade=parsed_trade)

    except (KeyError, ValueError, TypeError) as e:
        raise ValueError(f"Invalid data for trade event type {event_type}: {data}") from e
