from typing import Any

from pydantic import BaseModel, model_serializer

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.order_trigger import TriggerAbove, TriggerBelow


class ReplaceOrderDetails(BaseModel):
    """Corresponds to Rust's ReplaceOrder struct."""

    order_id: str  # The ID of the order to be replaced
    timestamp_ns: int  # Timestamp for this replace request
    new_price_limit: int | None = None
    new_quantity: int | None = None
    new_trigger: TriggerAbove | TriggerBelow | None = None
    book_quantity_decimals: int | None = None  # Assuming i8 maps to int
    book_price_decimals: int | None = None  # Assuming i8 maps to int

    # Pydantic serializes Optional[None] to null by default.
    # If specific fields must be present even if null, they don't need exclude_none.
    # If fields should be omitted if None, model_dump(exclude_none=True) is used by caller.


class ReplaceOrderRequestPayload(BaseModel):
    """
    Corresponds to Rust's orderbook_messages::actions::ReplaceOrderRequest struct,
    which is used as the payload in ObRequestPayload::ReplaceOrderRequest.
    The user_id field from Rust's ReplaceOrderRequest is handled by the SignedMessage wrapper.
    """

    request: ReplaceOrderDetails  # The actual replacement parameters
    user_id: str  # Added user_id field
    asset_id: AssetIdentifier  # Asset aidentifier for the order being replaced
    signature: list[int]  # Signature of the 'request' (ReplaceOrderDetails)
    post_sign_timestamp: int

    @model_serializer
    def serialize_model(self) -> dict[str, Any]:
        """Ensures the payload is correctly structured for the ObRequestPayload enum."""
        # This structure should match how CreateOrderRequest and CancelOrderRequest are serialized
        # for the ObRequestPayload enum in Rust, e.g., {"ReplaceOrderRequest": {...}}
        return {
            "request": self.request.model_dump(exclude_none=False),
            "signer": self.user_id,  # Added user_id to serialization
            "asset_id": self.asset_id.model_dump(exclude_none=True),
            "signature": self.signature,
            "post_sign_timestamp": self.post_sign_timestamp,
        }
