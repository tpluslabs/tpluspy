from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ValidationError, field_serializer

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.limit_order import LimitOrderDetails
from tplus.model.market_order import MarketOrderDetails
from tplus.model.order_trigger import TriggerAbove, TriggerBelow
from tplus.model.types import UserPublicKey

logger = logging.getLogger(__name__)


class Side(str, Enum):
    BUY = "Buy"
    SELL = "Sell"
    BID = "Buy"  # Alias for BUY
    ASK = "Sell"  # Alias for SELL

    @classmethod
    def _missing_(cls, value: object) -> Any:
        if isinstance(value, str):
            val_lower = value.lower()
            if val_lower == "bid":
                return cls.BUY
            if val_lower == "ask":
                return cls.SELL
        return super()._missing_(value)


class Order(BaseModel):
    signer: UserPublicKey
    order_id: str
    base_asset: AssetIdentifier
    book_price_decimals: int
    book_quantity_decimals: int
    details: LimitOrderDetails | MarketOrderDetails
    side: Side
    trigger: TriggerAbove | TriggerBelow | None = None
    creation_timestamp_ns: int
    canceled: bool = False

    def signable_part(self) -> str:
        return self.model_dump_json(exclude={"canceled"})

    @field_serializer("trigger")
    def serialize_trigger(self, trigger, _info):
        return None if trigger is None else trigger.model_dump()


class CreateOrderRequest(BaseModel):
    order: Order
    signature: list[int]
    post_sign_timestamp: int


class OrderResponse(BaseModel):
    order_id: str
    base_asset: AssetIdentifier
    side: Side
    limit_price: int | None
    quantity: int
    confirmed_filled_quantity: int
    pending_filled_quantity: int
    good_until_timestamp_ns: int | None
    timestamp_ns: int
    canceled: bool | None = None


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


class BaseOrderEvent(BaseModel):
    event_type: str


class OrderCreatedEvent(BaseOrderEvent):
    event_type: Literal["CREATED"]
    user_order: Order
    signature: list[int]
    book_timestamp_ns: int
    limit_overrides: Any | None = None
    limit_overrides_signature: Any | None = None


class OrderUpdatedEvent(BaseOrderEvent):
    event_type: Literal["UPDATED"]
    order_id: str
    status: str
    filled_quantity: int
    remaining_quantity: int
    update_timestamp_ns: int


class OrderCancelledEvent(BaseOrderEvent):
    event_type: Literal["CANCELED"]
    order_id: str
    asset_id: AssetIdentifier
    user_id: str
    timestamp_ns: int
    reason: str | None = None


class OrderReplacedEvent(BaseOrderEvent):
    event_type: Literal["REPLACED"]
    order_id: str
    asset_id: AssetIdentifier
    user_id: str
    new_quantity: int
    new_price: int


class OrderCreateFailedEvent(BaseOrderEvent):
    event_type: Literal["CREATEFAILED"]
    order_id: str
    reason: str | None = None


class OrderReplaceFailedEvent(BaseOrderEvent):
    event_type: Literal["REPLACEFAILED"]
    order_id: str
    reason: str | None = None


class OrderCancelFailedEvent(BaseOrderEvent):
    event_type: Literal["CANCELFAILED"]
    order_id: str
    reason: str | None = None


OrderEvent = (
    OrderCreatedEvent
    | OrderUpdatedEvent
    | OrderCancelledEvent
    | OrderReplacedEvent
    | OrderCreateFailedEvent
    | OrderReplaceFailedEvent
    | OrderCancelFailedEvent
)


_EVENT_TYPE_MODEL_MAP: dict[str, type[BaseOrderEvent]] = {
    "CREATED": OrderCreatedEvent,
    "UPDATED": OrderUpdatedEvent,
    "CANCELED": OrderCancelledEvent,
    "REPLACED": OrderReplacedEvent,
    "CREATEFAILED": OrderCreateFailedEvent,
    "REPLACEFAILED": OrderReplaceFailedEvent,
    "CANCELFAILED": OrderCancelFailedEvent,
}


def parse_order_event(data: dict[str, Any]) -> OrderEvent:
    """
    Parses an order event dictionary coming from the WebSocket stream.
    The server sends events in the form:
        {"Created": {<payload>}}, {"ReplaceFailed": {<payload>}}, ...
    This helper will:
    1. Extract the *single* event key.
    2. Determine the appropriate Pydantic model (using an explicit mapping).
    3. Instantiate and return the typed event object.
    """
    if not data or len(data) != 1:
        logger.error("Invalid order event structure: expected a single event key. Data: %s", data)
        raise ValueError(f"Invalid order event structure: expected a single event key, got {data}")

    event_type_key = next(iter(data.keys()))
    payload = data[event_type_key]

    if not isinstance(payload, dict):
        logger.error(
            "Invalid payload for event type %s: expected dict, got %s",
            event_type_key,
            type(payload),
        )
        raise ValueError(f"Invalid payload for event type {event_type_key}: {payload}")

    event_type_upper = event_type_key.upper()
    model_cls = _EVENT_TYPE_MODEL_MAP.get(event_type_upper)

    if model_cls is None:
        logger.error("Unrecognised order event type '%s'", event_type_key)
        raise ValueError(f"Unknown order event type: {event_type_key}")

    model_input = {"event_type": event_type_upper, **payload}

    try:
        return model_cls(**model_input)  # type: ignore[return-value]
    except ValidationError as ve:
        logger.error(
            "Validation error while parsing order event %s with model %s: %s. Payload: %s",
            event_type_upper,
            model_cls.__name__,
            ve,
            payload,
            exc_info=True,
        )
        raise
