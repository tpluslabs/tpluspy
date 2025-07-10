
from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier


class CancelOrder(BaseModel):
    """Data that will be serialized and signed for a cancel order operation."""

    order_id: str
    asset_id: AssetIdentifier  # Or str if only string form is signed
    signer: list[int]  # Public key of the signer, included in the signed payload


class CancelOrderRequest(BaseModel):
    """The payload for ObRequest representing a cancel order operation."""

    cancel: CancelOrder
    signature: list[int]  # Signature of the 'request' (ReplaceOrderDetails)
    post_sign_timestamp: int
