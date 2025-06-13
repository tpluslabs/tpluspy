from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Literal, Union

from pydantic import BaseModel, TypeAdapter, ValidationError, model_serializer

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.limit_order import LimitOrderDetails
from tplus.model.market_order import MarketOrderDetails

logger = logging.getLogger(__name__)


class Side(str, Enum):
    BUY = "Buy"
    SELL = "Sell"
    BID = "Buy"  # Alias for BUY (Side.BID is Side.BUY)
    ASK = "Sell"  # Alias for SELL (Side.ASK is Side.SELL)

    @classmethod
    def _missing_(cls, value: object) -> Any:
        if isinstance(value, str):
            val_lower = value.lower()
            if val_lower == "bid":
                return cls.BUY
            if val_lower == "ask":
                return cls.SELL
        return super()._missing_(value)  # Delegate to default if not BID/ASK


class Order(BaseModel):
    signer: list[int]
    order_id: str
    base_asset: AssetIdentifier
    details: LimitOrderDetails | MarketOrderDetails
    side: Side
    creation_timestamp_ns: int
    canceled: bool = False


class CreateOrderRequest(BaseModel):
    order: Order
    signature: list[int]

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, Any]]:
        # Replicates the old {"CreateOrderRequest": {...}} structure
        # Nested order will use its own (default) serializer
        request_data = {"order": self.order, "signature": self.signature}
        return {"CreateOrderRequest": request_data}


# --- Model for Order Data Received from GET Requests ---
# Represents the FLAT structure observed in API responses
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
    # Add other fields if observed in raw responses
    # signer: Optional[list[int]] = None # Example if signer is sometimes present


def parse_orders(orders_data: list[dict[str, Any]]) -> list[OrderResponse]:
    """
    Parses a list of order dictionaries (from GET API response) into OrderResponse objects.
    """
    parsed_orders = []
    if not isinstance(orders_data, list):
        logger.error(f"Expected a list for orders_data, got {type(orders_data)}")
        return []

    for order_dict in orders_data:
        try:
            # Attempt to parse the dictionary directly into the flat OrderResponse model
            order_response = OrderResponse(**order_dict)
            parsed_orders.append(order_response)
        except ValidationError as e:
            logger.warning(f"Skipping order due to validation error: {e}. Data: {order_dict}")
        except Exception as e:
            # Catch other potential errors during instantiation
            logger.warning(
                f"Skipping order due to unexpected parsing error: {e}. Data: {order_dict}"
            )

    return parsed_orders


# --- WebSocket Order Events ---


# Base class (optional, but can be useful)
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
    """Represents updates like partial fills or status changes."""

    event_type: Literal["UPDATED"]
    order_id: str
    # Include fields that can change, e.g.:
    status: str  # Example: FILLED, PARTIALLY_FILLED, CANCELLED
    filled_quantity: int
    remaining_quantity: int
    update_timestamp_ns: int
    # Optionally include the full updated order object if the stream sends it
    # order: Order | None = None


class OrderCancelledEvent(BaseOrderEvent):
    event_type: Literal["CANCELED"]
    order_id: str
    reason: str  # Example: "UserRequest", "System", "Expired"
    cancel_timestamp_ns: int


# --- ADD OrderReplacedEvent ---
class OrderReplacedEvent(BaseOrderEvent):
    event_type: Literal["REPLACED"]
    order_id: str  # The ID of the order that was replaced
    asset_id: AssetIdentifier
    user_id: str  # Public key of the user whose order was replaced
    new_quantity: int
    new_price: int
    # new_order_id: Optional[str] = None # If the replacement results in a new ID
    # replaced_timestamp_ns: Optional[int] = None # Timestamp of the replacement event


# --- END ADD OrderReplacedEvent ---


# Union type for type hinting
OrderEvent = Union[OrderCreatedEvent, OrderUpdatedEvent, OrderCancelledEvent, OrderReplacedEvent]


def parse_order_event(data: dict[str, Any]) -> OrderEvent:
    """Parses an order event dictionary from the WebSocket stream.
    Expects data in the format: {"EventTypeString": {event_payload_data}}
    e.g., {"Created": {"user_order": ..., "signature": ...}}
    """
    if not data or len(data) != 1:
        logger.error(f"Invalid order event structure: expected a single event key. Data: {data}")
        raise ValueError(f"Invalid order event structure: expected a single event key, got {data}")

    event_type_str_from_key = next(iter(data.keys()))
    actual_payload = data[event_type_str_from_key]

    if not isinstance(actual_payload, dict):
        logger.error(
            f"Invalid payload for event type {event_type_str_from_key}: Payload is not a dict. Payload: {actual_payload}"
        )
        raise ValueError(
            f"Invalid payload for event type {event_type_str_from_key}: {actual_payload}"
        )

    model_data_for_parsing = {"event_type": event_type_str_from_key.upper(), **actual_payload}

    try:
        adapter = TypeAdapter(OrderEvent)
        parsed_event = adapter.validate_python(model_data_for_parsing)
        return parsed_event
    except Exception as e:
        logger.error(
            f"Error during TypeAdapter parsing for order event ({event_type_str_from_key.upper()}): {e}. "
            f"Data used for parsing: {model_data_for_parsing}",
            exc_info=True,
        )
        raise ValueError(
            f"Data integrity issue or unexpected structure for order event type {event_type_str_from_key.upper()} during TypeAdapter: {actual_payload}"
        ) from e
