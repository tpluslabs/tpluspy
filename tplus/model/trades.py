from decimal import Decimal
from typing import Any, Literal, overload

from pydantic import BaseModel, Field

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.pagination import PageContinuation


class Trade(BaseModel):
    asset_id: AssetIdentifier
    trade_id: int
    order_id: str = ""  # Optional for basic trades
    price: Decimal
    quantity: Decimal
    timestamp_ns: int
    buyer_is_maker: bool = Field(..., description="True if the buyer was the maker")
    status: Literal["Pending", "Confirmed", "Rollbacked"] = "Confirmed"


class UserTrade(BaseModel):
    """User-specific trade data with comprehensive order and execution details."""

    asset_id: AssetIdentifier
    trade_id: int
    order_id: str
    price: Decimal
    quantity: Decimal
    timestamp_ns: int
    is_maker: bool = Field(..., description="True if this user was the maker")
    is_buyer: bool = Field(..., description="True if this user was the buyer")
    status: Literal["Pending", "Confirmed", "Rollbacked"]
    rollback_reason: str | None = None
    is_liquidation: bool = False
    is_auto_deleverage: bool = False
    sub_account: int = Field(
        default=0, description="Sub-account index (0=main/spot, 1=default margin)"
    )
    trading_fee: Decimal = Field(
        default=Decimal(0),
        description="Trading fee in USD; positive=paid, negative=rebate",
    )

    @property
    def buyer_is_maker(self) -> bool:
        """Derived field for compatibility - True if buyer was maker."""
        return self.is_buyer and self.is_maker


class HistoricalUserTrade(BaseModel):
    """A user-trade history row returned by MDS.

    One row may aggregate several fills for the same user, asset, and order
    within one database flush, so it deliberately has no individual trade ID.
    """

    asset_id: AssetIdentifier
    order_id: str
    price: Decimal
    quantity: Decimal
    timestamp_ns: int
    is_maker: bool
    is_buyer: bool
    status: Literal["Pending", "Confirmed", "Rollbacked"]
    rollback_reason: str | None = None
    is_liquidation: bool
    is_auto_deleverage: bool
    sub_account: int
    trading_fee: Decimal

    @property
    def buyer_is_maker(self) -> bool:
        return self.is_buyer and self.is_maker


def parse_trades(data: list[dict]) -> list[Trade]:
    return [
        Trade(
            asset_id=AssetIdentifier(item["asset_id"]),
            trade_id=item["trade_id"],
            order_id=item.get("order_id", ""),
            price=Decimal(item["price"]),
            quantity=Decimal(item["quantity"]),
            timestamp_ns=int(item["timestamp_ns"]),
            buyer_is_maker=item.get("buyer_is_maker", item.get("is_maker", False)),
            status=item.get("status", "Confirmed"),
        )
        for item in data
    ]


class UserTradesPage(PageContinuation):
    """One page of user trades plus continuation metadata.

    Behaves like a sequence of `HistoricalUserTrade` for existing list-style callers
    (`for trade in page`, `len(page)`, `page[i]`).
    """

    trades: list[HistoricalUserTrade]

    def __iter__(self):
        return iter(self.trades)

    def __len__(self) -> int:
        return len(self.trades)

    @overload
    def __getitem__(self, index: int) -> HistoricalUserTrade: ...

    @overload
    def __getitem__(self, index: slice) -> list[HistoricalUserTrade]: ...

    def __getitem__(self, index: int | slice) -> HistoricalUserTrade | list[HistoricalUserTrade]:
        return self.trades[index]

    def __bool__(self) -> bool:
        return bool(self.trades)

    def __contains__(self, item: object) -> bool:
        return item in self.trades

    def __eq__(self, other: object) -> bool:
        if isinstance(other, list):
            return self.trades == other
        return super().__eq__(other)


def parse_user_trades(data: list[dict]) -> list[UserTrade]:
    """Parse live or OMS user trades."""
    return [UserTrade.model_validate(item) for item in data]


def parse_historical_user_trades(data: list[dict]) -> list[HistoricalUserTrade]:
    """Parse MDS user history into durable trade records."""
    return [HistoricalUserTrade.model_validate(item) for item in data]


def parse_user_trades_page(data: list[dict] | dict) -> UserTradesPage:
    if isinstance(data, list):
        trades = parse_historical_user_trades(data)
        return UserTradesPage(trades=trades)
    return UserTradesPage(
        trades=parse_historical_user_trades(data.get("trades", [])),
        has_next_page=bool(data.get("has_next_page", False)),
        next_page=data.get("next_page"),
    )


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
        return Trade.model_validate(item)
    except Exception as err:
        raise ValueError(f"Invalid single trade data: {item}. Err={err}") from err


def parse_single_user_trade(item: dict[str, Any]) -> UserTrade:
    """Parses a single user trade dictionary into a UserTrade object."""
    try:
        return UserTrade(
            asset_id=AssetIdentifier(item["asset_id"]),
            trade_id=item["trade_id"],
            order_id=item["order_id"],
            price=Decimal(item["price"]),
            quantity=Decimal(item["quantity"]),
            timestamp_ns=int(item["timestamp_ns"]),
            is_maker=bool(item["is_maker"]),
            is_buyer=bool(item["is_buyer"]),
            status=item["status"],
            rollback_reason=item.get("rollback_reason"),
            is_liquidation=bool(item.get("is_liquidation", False)),
            is_auto_deleverage=bool(item.get("is_auto_deleverage", False)),
            sub_account=int(item.get("sub_account", 0)),
            trading_fee=Decimal(str(item.get("trading_fee", 0))),
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
