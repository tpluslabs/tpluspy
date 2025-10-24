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
    return [
        UserTrade(
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
        for item in data
    ]


class BaseTradeEvent(BaseModel):
    event_type: str


class TradePendingEvent(BaseTradeEvent):
    """Represents a trade that has occurred but is awaiting final confirmation."""

    event_type: Literal["PENDING"] = Field(default="PENDING")
    order_id: str
    match_id: str  # Or some identifier for the match
    price: float
    quantity: int
    timestamp_ns: int


class TradeConfirmedEvent(BaseTradeEvent):
    """Represents a finalized trade."""

    event_type: Literal["CONFIRMED"] = Field(default="CONFIRMED")
    trade: Trade


TradeEvent = TradePendingEvent | TradeConfirmedEvent


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
    if len(data.keys()) == 0:
        raise ValueError("Empty trade event")

    event_type = list(data.keys())[0]

    if not event_type or event_type not in ["Confirmed", "Pending"]:
        raise ValueError(f"Invalid trade event structure: {data}")

    payload = data.get(event_type)

    try:
        if event_type == "Pending":
            return TradePendingEvent(
                order_id=payload["order_id"],
                match_id=payload["match_id"],
                price=float(payload["price"]),
                quantity=int(payload["quantity"]),
                timestamp_ns=int(payload["timestamp_ns"]),
            )

        elif event_type == "Confirmed":
            parsed_trade = parse_single_trade(payload)
            return TradeConfirmedEvent(trade=parsed_trade)

        else:
            raise ValueError(f"Unknown trade event type: {event_type}")

    except (KeyError, ValueError, TypeError) as e:
        raise ValueError(f"Invalid data for trade event type {event_type}: {data}") from e
