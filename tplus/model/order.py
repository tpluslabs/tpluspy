import logging
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, ValidationError, model_serializer

from tplus.model.asset_identifier import IndexAsset
from tplus.model.limit_order import LimitOrderDetails
from tplus.model.market_order import MarketOrderDetails

logger = logging.getLogger(__name__)

class Order(BaseModel):
    signer: list[int]
    order_id: str
    base_asset: IndexAsset
    details: LimitOrderDetails | MarketOrderDetails
    side: str
    creation_timestamp_ns: int


class CreateOrderRequest(BaseModel):
    order: Order
    signature: list[int]

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, Any]]:
        # Replicates the old {"CreateOrderRequest": {...}} structure
        # Nested order will use its own (default) serializer
        request_data = {
            "order": self.order,
            "signature": self.signature
        }
        return {"CreateOrderRequest": request_data}


# --- Model for Order Data Received from GET Requests ---
# Represents the FLAT structure observed in API responses
class OrderResponse(BaseModel):
    order_id: str
    base_asset: IndexAsset
    side: str
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
            logger.warning(f"Skipping order due to unexpected parsing error: {e}. Data: {order_dict}")

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
    status: str # Example: FILLED, PARTIALLY_FILLED, CANCELLED
    filled_quantity: int
    remaining_quantity: int
    update_timestamp_ns: int
    # Optionally include the full updated order object if the stream sends it
    # order: Order | None = None


class OrderCancelledEvent(BaseOrderEvent):
    event_type: Literal["CANCELLED"] = Field(default="CANCELLED")
    order_id: str
    reason: str # Example: "UserRequest", "System", "Expired"
    cancel_timestamp_ns: int

# Union type for type hinting
OrderEvent = Union[OrderCreatedEvent, OrderUpdatedEvent, OrderCancelledEvent]

def parse_order_event(data: dict[str, Any]) -> OrderEvent:
    """Parses an order event dictionary from the WebSocket stream."""
    event_type = data.get('event_type')
    payload = data.get('payload', {}) # Assume payload contains the event data

    if not event_type or not isinstance(payload, dict):
        raise ValueError(f"Invalid order event structure: {data}")

    try:
        if event_type == "CREATED":
            # Assume payload is the raw order dictionary
            # We need a way to parse a single order dict, let's reuse/adapt parse_orders logic
            # For simplicity, let's assume parse_orders can handle a single dict or adapt it.
            # Hacky approach: wrap in list and get first element
            if not (parsed_order_list := parse_orders([payload])):
                 raise ValueError(f"Failed to parse order data in CREATED event: {payload}")
            return OrderCreatedEvent(order=parsed_order_list[0])

        elif event_type == "UPDATED":
            # Assuming payload directly contains the fields for OrderUpdatedEvent
            return OrderUpdatedEvent(
                order_id=payload['order_id'],
                status=payload['status'],
                filled_quantity=int(payload['filled_quantity']),
                remaining_quantity=int(payload['remaining_quantity']),
                update_timestamp_ns=int(payload['update_timestamp_ns'])
                # Parse optional full order if present
            )

        elif event_type == "CANCELLED":
            # Assuming payload directly contains the fields for OrderCancelledEvent
            return OrderCancelledEvent(
                order_id=payload['order_id'],
                reason=payload['reason'],
                cancel_timestamp_ns=int(payload['cancel_timestamp_ns'])
            )

        else:
            logger.warning(f"Received unknown order event type: {event_type}. Data: {data}")
            # Option: return a generic event or raise an error
            raise ValueError(f"Unknown order event type: {event_type}")

    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Error parsing order event ({event_type}): {e}. Data: {data}")
        raise ValueError(f"Invalid data for order event type {event_type}: {data}") from e


