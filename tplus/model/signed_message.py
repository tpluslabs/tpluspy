from pydantic import BaseModel
from typing import Union

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.order import CreateOrderRequest
from tplus.model.cancel_order import CancelOrderRequest


class ObRequest(BaseModel):
    order_id: str
    base_asset: AssetIdentifier
    ob_request_payload: Union[CreateOrderRequest, CancelOrderRequest]


class SignedMessage(BaseModel):
    payload: ObRequest
    user_id: str
    post_sign_timestamp: int
