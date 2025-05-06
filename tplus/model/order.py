import logging
from typing import Any, Literal, Optional, Union
from enum import Enum

from pydantic import BaseModel, Field, ValidationError, model_serializer

from tplus.model.asset_identifier import IndexAsset
from tplus.model.limit_order import LimitOrderDetails
from tplus.model.market_order import MarketOrderDetails

logger = logging.getLogger(__name__)

class Side(Enum):
    BUY = "Buy"
    SELL = "Sell"

class Order(BaseModel):
    signer: list[int]
    order_id: str
    base_asset: IndexAsset
    details: LimitOrderDetails | MarketOrderDetails
    side: Side
    creation_timestamp_ns: int


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
    base_asset: IndexAsset
    side: Side
    limit_price: Optional[int]
    quantity: int
    confirmed_filled_quantity: int
    pending_filled_quantity: int
    good_until_timestamp_ns: Optional[int]
    timestamp_ns: int
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
    event_type: Literal["CREATED"] = Field(default="CREATED")
    order: Order


class OrderUpdatedEvent(BaseOrderEvent):
    """Represents updates like partial fills or status changes."""

    event_type: Literal["UPDATED"] = Field(default="UPDATED")
    order_id: str
    # Include fields that can change, e.g.:
    status: str  # Example: FILLED, PARTIALLY_FILLED, CANCELLED
    filled_quantity: int
    remaining_quantity: int
    update_timestamp_ns: int
    # Optionally include the full updated order object if the stream sends it
    # order: Order | None = None


class OrderCancelledEvent(BaseOrderEvent):
    event_type: Literal["CANCELLED"] = Field(default="CANCELLED")
    order_id: str
    reason: str  # Example: "UserRequest", "System", "Expired"
    cancel_timestamp_ns: int


class OrderCreateFailedEvent(BaseOrderEvent):
    event_type: Literal["CREATE_FAILED"] = Field(default="CREATE_FAILED")
    order_id: str


class OrderReplaceFailedEvent(BaseOrderEvent):
    event_type: Literal["REPLACE_FAILED"] = Field(default="REPLACE_FAILED")
    order_id: str


class OrderCancelFailedEvent(BaseOrderEvent):
    event_type: Literal["CANCEL_FAILED"] = Field(default="CANCEL_FAILED")
    order_id: str


# Union type for type hinting
OrderEvent = Union[
    OrderCreatedEvent,
    OrderUpdatedEvent,
    OrderCancelledEvent,
    OrderCreateFailedEvent,
    OrderReplaceFailedEvent,
    OrderCancelFailedEvent,
]


def parse_order_event(data: dict[str, Any]) -> OrderEvent:
    """Parses an order event dictionary from the WebSocket stream."""
    # Handle the actual server event format
    if "Created" in data:
        order_data = data["Created"]["user_order"]
        # Ensure 'side' is converted to Enum if it's a string from the raw data
        if "side" in order_data and isinstance(order_data["side"], str):
            try:
                order_data["side"] = Side(order_data["side"].capitalize()) # Attempt to map e.g. "buy" or "BUY" to "Buy"
            except ValueError:
                try:
                    order_data["side"] = Side[order_data["side"].upper()] # Attempt to map e.g. "BUY" to Side.BUY enum member name
                except (ValueError, KeyError) as e:
                    logger.warning(f"Invalid side value '{order_data['side']}' in Created event, cannot map to Side enum: {e}")
                    # If critical, re-raise or handle as an error. For now, parsing might fail later.

        # Handle nested details structure
        if "details" in order_data and isinstance(order_data["details"], dict):
            details = order_data["details"]
            if "Limit" in details:
                limit_details = details["Limit"]
                # Convert hex strings to integers if needed
                if isinstance(limit_details["limit_price"], str) and limit_details["limit_price"].startswith("0x"):
                    limit_details["limit_price"] = int(limit_details["limit_price"], 16)
                if isinstance(limit_details["quantity"], str) and limit_details["quantity"].startswith("0x"):
                    limit_details["quantity"] = int(limit_details["quantity"], 16)
                # Flatten the time_in_force structure
                if "time_in_force" in limit_details and "GTC" in limit_details["time_in_force"]:
                    limit_details["time_in_force"] = limit_details["time_in_force"]["GTC"]
                order_data["details"] = limit_details
        return OrderCreatedEvent(order=Order(**order_data))
    elif "Updated" in data:
        update_data = data["Updated"]
        return OrderUpdatedEvent(
            order_id=update_data["order_id"],
            status=update_data.get("status", "UPDATED"),
            filled_quantity=int(update_data.get("filled_quantity", 0)),
            remaining_quantity=int(update_data.get("remaining_quantity", 0)),
            update_timestamp_ns=int(update_data.get("book_timestamp_ns", 0))
        )
    elif "Canceled" in data:
        cancel_data = data["Canceled"]
        return OrderCancelledEvent(
            order_id=cancel_data["order_id"],
            reason=cancel_data.get("reason", "Unknown"),
            cancel_timestamp_ns=int(cancel_data.get("book_timestamp_ns", 0))
        )
    elif "CreateFailed" in data:
        return OrderCreateFailedEvent(order_id=data["CreateFailed"]["order_id"])
    elif "ReplaceFailed" in data:
        return OrderReplaceFailedEvent(order_id=data["ReplaceFailed"]["order_id"])
    elif "CancelFailed" in data:
        return OrderCancelFailedEvent(order_id=data["CancelFailed"]["order_id"])
    else:
        raise ValueError(f"Unknown order event structure: {data}")


# --- REST API Cancel/Replace Responses ---

class CancelOrderStatus(str, Enum):
    RECEIVED = "Received"
    REJECTED = "Rejected"

class CancelOrderResponse(BaseModel):
    order_id: str
    status: CancelOrderStatus

class ReplaceOrderStatus(str, Enum):
    RECEIVED = "Received"
    REJECTED = "Rejected"

class ReplaceOrderResponse(BaseModel):
    order_id: str # ID of the *original* order being replaced
    status: ReplaceOrderStatus
