from pydantic import BaseModel

from tplus.model.asset_identifier import IndexAsset
from tplus.model.order import CreateOrderRequest


class ObRequest(BaseModel):
    order_id: str
    base_asset: IndexAsset
    ob_request_payload: CreateOrderRequest


class SignedMessage(BaseModel):
    payload: ObRequest
    user_id: str
    post_sign_timestamp: int
