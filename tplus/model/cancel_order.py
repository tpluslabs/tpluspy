from typing import Any

from pydantic import BaseModel, model_serializer

from tplus.model.asset_identifier import AssetIdentifier


class CancelOrder(BaseModel):
    """Data that will be serialized and signed for a cancel order operation."""

    order_id: str
    asset_identifier: AssetIdentifier  # Or str if only string form is signed
    signer: str  # Public key of the signer, included in the signed payload


class CancelOrderRequest(BaseModel):
    """The payload for ObRequest representing a cancel order operation."""

    cancel: CancelOrder
    signature: list[int]  # Signature of the 'request' (ReplaceOrderDetails)
    post_sign_timestamp: int

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, Any]]:
        # This will ensure model_dump() returns {"CancelOrderRequest": {"order_id": self.order_id}}
        # to match the Rust ObRequestPayload::CancelOrderRequest enum variant.
        return {
            "CancelOrderRequest": {
                "cancel": self.cancel,
                "signature": self.signature,
                "post_sign_timestamp": self.post_sign_timestamp,
            }
        }
