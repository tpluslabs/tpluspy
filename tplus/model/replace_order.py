from typing import Any

from pydantic import BaseModel, Field, model_serializer

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.multisig import AdditionalSigner
from tplus.model.order_id import UserOrderId
from tplus.model.order_trigger import TriggerAbove, TriggerBelow


class ReplaceOrderDetails(BaseModel):
    """Corresponds to Rust's ReplaceOrder struct.

    Carries the **complete effective terms** the order will have once the replacement is
    installed — not a sparse patch. Every mutable term is mandatory so that the OMS,
    orderbook and clearing engine all derive the same effective order from the same signed
    bytes, and so chained replacements compose instead of silently reinstating superseded
    terms from the originally signed order.

    Field order must mirror the Rust struct exactly: the signature is over the
    whitespace-stripped JSON, so declaration order is part of the wire contract.
    """

    order_id: UserOrderId  # The ID of the order to be replaced
    base_asset: AssetIdentifier
    timestamp_ns: int  # Timestamp for this replace request
    new_price_limit: int  # Effective limit price after the replacement
    new_quantity: int  # Effective LIFETIME-TOTAL quantity (not the remaining part)
    # Effective trigger state. ``None`` means "no trigger", NOT "leave the trigger alone" —
    # a replacement that keeps a trigger must restate it.
    new_trigger: TriggerAbove | TriggerBelow | None = None
    book_quantity_decimals: int  # i8 in Rust
    book_price_decimals: int  # i8 in Rust
    protocol_version: int = 1


class ReplaceOrderRequestPayload(BaseModel):
    """
    Corresponds to Rust's orderbook_messages::actions::ReplaceOrderRequest struct,
    which is used as the payload in ObRequestPayload::ReplaceOrderRequest.
    The user_id field from Rust's ReplaceOrderRequest is handled by the SignedMessage wrapper.
    """

    request: ReplaceOrderDetails  # The actual replacement parameters
    user_id: str  # Added user_id field
    signature: list[int]  # Signature of the 'request' (ReplaceOrderDetails)
    post_sign_timestamp: int
    additional_signers: list[AdditionalSigner] = Field(default_factory=list)

    @model_serializer
    def serialize_model(self) -> dict[str, Any]:
        """Ensures the payload is correctly structured for the ObRequestPayload enum."""
        # This structure should match how CreateOrderRequest and CancelOrderRequest are serialized
        # for the ObRequestPayload enum in Rust, e.g., {"ReplaceOrderRequest": {...}}
        return {
            "request": self.request.model_dump(exclude_none=False),
            "signer": self.user_id,  # Added user_id to serialization
            "signature": self.signature,
            "post_sign_timestamp": self.post_sign_timestamp,
            "additional_signers": self.additional_signers,
        }
