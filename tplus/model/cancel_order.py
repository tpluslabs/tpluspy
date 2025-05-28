from pydantic import BaseModel, model_serializer
from typing import List, Dict, Any

from tplus.model.asset_identifier import AssetIdentifier

class CancelOrderDataToSign(BaseModel):
    """ Data that will be serialized and signed for a cancel order operation. """
    order_id: str
    asset_identifier: AssetIdentifier # Or str if only string form is signed
    user_id: str # Public key of the signer, included in the signed payload
    cancel_timestamp_ns: int

class CancelOrderRequest(BaseModel):
    """ The payload for ObRequest representing a cancel order operation. """
    order_id: str

    @model_serializer
    def serialize_model(self) -> Dict[str, Dict[str, Any]]:
        # This will ensure model_dump() returns {"CancelOrderRequest": {"order_id": self.order_id}}
        # to match the Rust ObRequestPayload::CancelOrderRequest enum variant.
        return {"CancelOrderRequest": {"order_id": self.order_id}} 