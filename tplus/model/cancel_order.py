from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.order_id import UserOrderId
from tplus.model.types import UserPublicKey


class CancelOrder(BaseModel):
    """The order a cancel names."""

    signer: UserPublicKey
    order_id: UserOrderId
    asset_id: AssetIdentifier
    protocol_version: int = 1


class CancelOrderRequest(BaseModel):
    """The payload for ObRequest representing a cancel order operation."""

    cancel: CancelOrder
    post_sign_timestamp: int
