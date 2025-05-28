from pydantic import BaseModel, model_serializer
from typing import Union, Any, Dict

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.order import CreateOrderRequest
from tplus.model.cancel_order import CancelOrderRequest
from tplus.model.replace_order import ReplaceOrderRequestPayload


class ObRequest(BaseModel):
    order_id: str
    base_asset: AssetIdentifier
    ob_request_payload: Union[CreateOrderRequest, CancelOrderRequest, ReplaceOrderRequestPayload]

    @model_serializer
    def serialize_model(self) -> Dict[str, Any]:
        data = {
            "order_id": self.order_id,
            "base_asset": self.base_asset.model_dump(),
        }
        if isinstance(self.ob_request_payload, (CreateOrderRequest, CancelOrderRequest, ReplaceOrderRequestPayload)):
            data["ob_request_payload"] = self.ob_request_payload.model_dump(exclude_none=False)
        else:
            raise TypeError(
                f"Unexpected type for ob_request_payload: {type(self.ob_request_payload)}. "
                f"Expected CreateOrderRequest, CancelOrderRequest, or ReplaceOrderRequestPayload."
            )
        return data


class SignedMessage(BaseModel):
    payload: ObRequest
    user_id: str
    post_sign_timestamp: int
