import logging
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, overload

from pydantic import BaseModel, Field, ValidationError, field_serializer

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.limit_order import LimitOrderDetails
from tplus.model.market_order import MarketOrderDetails
from tplus.model.multisig import AdditionalSigner
from tplus.model.order_id import UserOrderId
from tplus.model.order_trigger import OrderTrigger
from tplus.model.pagination import PageContinuation
from tplus.model.types import UserPublicKey

logger = logging.getLogger(__name__)


class TradeTarget(BaseModel):
    """Identifies which sub-account and balance type to use for a trade.

    Corresponds to the Rust TradeTarget struct in orderbook_messages.
    """

    account: int = 0
    """Offset into trader's subaccounts (0 = main account, 1 = margin account)."""
    is_spot: bool = True
    """Whether to spend from spot balance (True) or margin balance (False)."""

    @classmethod
    def main_account_spot_trade(cls) -> "TradeTarget":
        """Trade target set to main account spending spot balance."""
        return cls(account=0, is_spot=True)

    @classmethod
    def margin_account_spot_trade(cls) -> "TradeTarget":
        """Trade target set to margin account spending spot balance."""
        return cls(account=1, is_spot=True)

    @classmethod
    def margin_account_margin_trade(cls) -> "TradeTarget":
        """Trade target set to margin account spending margin balance."""
        return cls(account=1, is_spot=False)


class Side(str, Enum):
    BUY = "Buy"
    SELL = "Sell"
    BID = "Buy"  # Alias for BUY
    ASK = "Sell"  # Alias for SELL

    @classmethod
    def _missing_(cls, value: object) -> Any:
        if isinstance(value, str):
            val_lower = value.lower()
            if val_lower in ("buy", "bid"):
                return cls.BUY
            if val_lower in ("sell", "ask"):
                return cls.SELL
        return super()._missing_(value)


class Order(BaseModel):
    signer: UserPublicKey
    order_id: UserOrderId
    base_asset: AssetIdentifier
    book_price_decimals: int
    book_quantity_decimals: int
    details: LimitOrderDetails | MarketOrderDetails
    side: Side
    trigger: OrderTrigger | None = None
    creation_timestamp_ns: int
    target: TradeTarget = TradeTarget.margin_account_spot_trade()
    reduce_only: bool = False
    max_trading_fees_rate: int = 50_000
    protocol_version: int = 1

    def signable_part(self) -> str:
        return self.model_dump_json()

    @field_serializer("trigger")
    def serialize_trigger(self, trigger, _info):
        return None if trigger is None else trigger.model_dump()


class CreateOrderRequest(BaseModel):
    order: Order
    signature: list[int]
    post_sign_timestamp: int
    additional_signers: list[AdditionalSigner] = Field(default_factory=list)


class OrderResponse(BaseModel):
    order_id: str
    base_asset: AssetIdentifier
    side: Side
    limit_price: Decimal | None
    quantity: Decimal | None
    amount: Decimal | None
    max_sellable_amount: Decimal | None
    max_sellable_quantity: Decimal | None
    confirmed_filled_quantity: Decimal
    pending_filled_quantity: Decimal
    confirmed_filled_amount: Decimal
    pending_filled_amount: Decimal
    confirmed_trading_fees_amount: Decimal
    pending_trading_fees_amount: Decimal
    good_until_timestamp_ns: int | None
    timestamp_ns: int
    in_flight: bool | None = None
    canceled: bool | None = None
    status: str
    trigger_above_price: Decimal | None
    trigger_below_price: Decimal | None
    trigger_touched: bool | None = None
    parent_id: str | None = None
    last_update_timestamp_ns: int | None
    is_immediate_or_cancel: bool | None = None
    is_fill_or_kill: bool | None = None
    is_liquidation: bool | None = None
    is_auto_deleverage: bool | None = None
    is_reduce_only: bool | None = None
    trigger_enabled_quantity: Decimal | None = None


class HistoricalUserOrder(BaseModel):
    """Compact order-history row returned by MDS."""

    order_id: str
    base_asset: AssetIdentifier
    account_index: int
    is_spot: bool
    side: Side
    limit_price: Decimal | None
    quantity: Decimal | None
    amount: Decimal | None
    confirmed_filled_quantity: Decimal
    confirmed_filled_amount: Decimal
    confirmed_trading_fees_amount: Decimal
    good_until_timestamp_ns: int | None
    timestamp_ns: int
    is_immediate_or_cancel: bool
    is_fill_or_kill: bool
    is_liquidation: bool
    is_auto_deleverage: bool
    is_reduce_only: bool
    canceled: bool
    status: str
    trigger_above_price: Decimal | None
    trigger_below_price: Decimal | None
    trigger_touched: bool | None
    trigger_enabled_quantity: Decimal | None
    parent_id: str | None
    last_update_timestamp_ns: int


def parse_orders(orders_data: list[dict[str, Any]]) -> list[OrderResponse]:
    parsed_orders = []
    if not isinstance(orders_data, list):
        logger.error(f"Expected a list for orders_data, got {type(orders_data)} | {orders_data}")
        return []

    for order_dict in orders_data:
        try:
            order_response = OrderResponse(**order_dict)
            parsed_orders.append(order_response)
        except ValidationError as e:
            logger.warning(f"Skipping order due to validation error: {e}. Data: {order_dict}")
        except Exception as e:
            logger.warning(
                f"Skipping order due to unexpected parsing error: {e}. Data: {order_dict}"
            )

    return parsed_orders


class UserOrdersPage(PageContinuation):
    """One page of user orders plus continuation metadata.

    Behaves like a sequence of `HistoricalUserOrder` for existing list-style callers
    (`for order in page`, `len(page)`, `page[i]`).
    """

    orders: list[HistoricalUserOrder]

    def __iter__(self):
        return iter(self.orders)

    def __len__(self) -> int:
        return len(self.orders)

    @overload
    def __getitem__(self, index: int) -> HistoricalUserOrder: ...

    @overload
    def __getitem__(self, index: slice) -> list[HistoricalUserOrder]: ...

    def __getitem__(self, index: int | slice) -> HistoricalUserOrder | list[HistoricalUserOrder]:
        return self.orders[index]

    def __bool__(self) -> bool:
        return bool(self.orders)

    def __contains__(self, item: object) -> bool:
        return item in self.orders

    def __eq__(self, other: object) -> bool:
        if isinstance(other, list):
            return self.orders == other
        return super().__eq__(other)


def parse_user_orders_page(data: list[dict] | dict) -> UserOrdersPage:
    if isinstance(data, list):
        orders = [HistoricalUserOrder.model_validate(item) for item in data]
        return UserOrdersPage(orders=orders)

    orders = [HistoricalUserOrder.model_validate(item) for item in data.get("orders", [])]
    return UserOrdersPage(
        orders=orders,
        has_next_page=bool(data.get("has_next_page", False)),
        next_page=data.get("next_page"),
    )


class BaseOrderEvent(BaseModel):
    event_type: str


class OrderCreatedEvent(BaseOrderEvent):
    """``OrderEvent::Created`` -- the OMS sends the full book ``Order``."""

    event_type: Literal["CREATED"]
    user_order: Order
    signature: list[int]
    book_timestamp_ns: int
    limit_overrides: Any | None = None
    limit_overrides_signature: Any | None = None
    amend_overrides: Any | None = None
    trigger_touched: bool | None = None
    is_liquidation: bool = False
    is_auto_deleverage: bool = False

    @property
    def order_id(self) -> str:
        return self.user_order.order_id


class OrderUpdatedEvent(BaseOrderEvent):
    """Legacy ``{"type": "updated", ...}`` shape. The OMS ``/orders`` stream never
    emits it (fills are reported on ``/trades/user/events``); kept for callers that
    constructed it themselves."""

    event_type: Literal["UPDATED"]
    order_id: str
    status: str
    filled_quantity: int
    remaining_quantity: int
    update_timestamp_ns: int


class OrderCancelledEvent(BaseOrderEvent):
    """``OrderEvent::Canceled`` (``orderbook_messages::events::OrderCanceled``)."""

    event_type: Literal["CANCELED"]
    order_id: str
    asset_id: AssetIdentifier
    user_id: str
    timestamp_ns: int
    operator_pubkey: str | None = None
    initial_receive_timestamp_ns: int | None = None
    reason: str | None = None


class OrderRemovedEvent(BaseOrderEvent):
    """``OrderEvent::Removed`` (``orderbook_messages::events::OrderRemoved``).

    ``reason`` is one of ``Completed``, ``Canceled``, ``Expired``, ``Rejected``,
    ``SelfTradePrevented``.
    """

    event_type: Literal["REMOVED"]
    order_id: str
    asset_id: AssetIdentifier
    user_id: str
    timestamp_ns: int
    operator_pubkey: str | None = None
    reason: str
    filled_quantity: int = 0
    confirmed_quantity: int = 0
    filled_amount: int = 0
    confirmed_amount: int = 0
    book_quantity_decimals: int = 0
    initial_receive_timestamp_ns: int | None = None


class OrderReplacedEvent(BaseOrderEvent):
    """``OrderEvent::Replaced`` (``orderbook_messages::events::OrderUpdated``)."""

    event_type: Literal["REPLACED"]
    order_id: str
    asset_id: AssetIdentifier
    user_id: str
    new_quantity: int
    new_price: int
    timestamp_ns: int | None = None
    authorization_revision: int = 0
    operator_pubkey: str | None = None
    initial_receive_timestamp_ns: int | None = None


class OrderAmendedEvent(BaseOrderEvent):
    """``OrderEvent::Amended`` (``orderbook_messages::events::OrderAmended``)."""

    event_type: Literal["AMENDED"]
    order_id: str
    asset_id: AssetIdentifier
    user_id: str
    new_quantity: int
    remaining_quantity: int
    authorization_revision: int = 0
    book_quantity_decimals: int = 0
    timestamp_ns: int | None = None
    operator_pubkey: str | None = None


class OrderTriggeredEvent(BaseOrderEvent):
    """``OrderEvent::Triggered`` (``orderbook_messages::events::OrderTriggered``)."""

    event_type: Literal["TRIGGERED"]
    order_id: str
    asset_id: AssetIdentifier
    user_id: str
    timestamp_ns: int
    quantity: int
    trigger_touched: bool
    operator_pubkey: str | None = None


class OrderCreateFailedEvent(BaseOrderEvent):
    event_type: Literal["CREATEFAILED"]
    order_id: str
    user_id: str
    reason: str | None = None


class OrderReplaceFailedEvent(BaseOrderEvent):
    event_type: Literal["REPLACEFAILED"]
    order_id: str
    user_id: str
    reason: str | None = None


class OrderAmendFailedEvent(BaseOrderEvent):
    event_type: Literal["AMENDFAILED"]
    order_id: str
    user_id: str
    reason: str | None = None


class OrderCancelFailedEvent(BaseOrderEvent):
    event_type: Literal["CANCELFAILED"]
    order_id: str
    user_id: str
    reason: str | None = None


OrderEvent = (
    OrderCreatedEvent
    | OrderUpdatedEvent
    | OrderCancelledEvent
    | OrderRemovedEvent
    | OrderReplacedEvent
    | OrderAmendedEvent
    | OrderTriggeredEvent
    | OrderCreateFailedEvent
    | OrderReplaceFailedEvent
    | OrderAmendFailedEvent
    | OrderCancelFailedEvent
)


_EVENT_TYPE_MODEL_MAP: dict[str, type[BaseOrderEvent]] = {
    "CREATED": OrderCreatedEvent,
    "UPDATED": OrderUpdatedEvent,
    "CANCELED": OrderCancelledEvent,
    "REMOVED": OrderRemovedEvent,
    "REPLACED": OrderReplacedEvent,
    "AMENDED": OrderAmendedEvent,
    "TRIGGERED": OrderTriggeredEvent,
    "CREATEFAILED": OrderCreateFailedEvent,
    "REPLACEFAILED": OrderReplaceFailedEvent,
    "AMENDFAILED": OrderAmendFailedEvent,
    "CANCELFAILED": OrderCancelFailedEvent,
}


def _normalise_event_type(raw: str) -> str:
    return raw.replace("_", "").upper()


def _split_order_event(data: Any) -> tuple[str, dict[str, Any]]:
    """Return ``(event_type, fields)`` for either wire shape of an order event.

    The OMS ``/orders`` stream serializes the Rust ``tplus_client::OrderEvent`` enum
    with serde's default *external* tagging -- one key naming the variant, whose
    value holds the fields: ``{"Removed": {"order_id": ..., ...}}``. The older
    internally tagged form ``{"type": "removed", "order_id": ...}`` is still accepted.
    """
    if not isinstance(data, dict):
        raise ValueError(f"Invalid order event structure: expected an object, got {data!r}")

    type_key = data.get("type")
    if isinstance(type_key, str):
        return _normalise_event_type(type_key), {k: v for k, v in data.items() if k != "type"}

    if len(data) == 1:
        (variant, fields), *_ = data.items()
        if isinstance(variant, str) and _normalise_event_type(variant) in _EVENT_TYPE_MODEL_MAP:
            if not isinstance(fields, dict):
                raise ValueError(
                    f"Invalid order event structure: variant {variant!r} payload is not an "
                    f"object, got {fields!r}"
                )
            return _normalise_event_type(variant), fields

    raise ValueError(
        "Invalid order event structure: expected {'type': ...} or a single-variant "
        f"object such as {{'Removed': {{...}}}}, got {data!r}"
    )


def parse_order_event(data: Any) -> OrderEvent:
    try:
        event_type_upper, fields = _split_order_event(data)
    except ValueError:
        logger.error("Invalid order event structure. Data: %s", data)
        raise

    model_cls = _EVENT_TYPE_MODEL_MAP.get(event_type_upper)
    if model_cls is None:
        logger.error("Unrecognised order event type '%s'", event_type_upper)
        raise ValueError(f"Unknown order event type: {event_type_upper}")

    try:
        return model_cls(event_type=event_type_upper, **fields)  # type: ignore[return-value]
    except ValidationError as ve:
        logger.error(
            "Validation error while parsing order event %s with model %s: %s. Payload: %s",
            event_type_upper,
            model_cls.__name__,
            ve,
            data,
            exc_info=True,
        )
        raise


# ---------------------------------------------------------------------------
# HTTP response models for create/replace/cancel (mirror OMS endpoints)
# ---------------------------------------------------------------------------


class OperationStatus(str, Enum):
    RECEIVED = "Received"
    REJECTED = "Rejected"


class OrderOperationResponse(BaseModel):
    order_id: str
    status: OperationStatus
    reason: str | None = None
    processed_at_ns: int | None = None
