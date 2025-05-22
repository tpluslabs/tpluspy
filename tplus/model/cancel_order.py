from pydantic import BaseModel
from typing import List

from tplus.model.asset_identifier import AssetIdentifier

class CancelOrderDataToSign(BaseModel):
    """ Data that will be serialized and signed for a cancel order operation. """
    order_id: str
    asset_identifier: AssetIdentifier # Or str if only string form is signed
    user_id: str # Public key of the signer, included in the signed payload
    cancel_timestamp_ns: int

class CancelOrderRequest(BaseModel):
    """ The payload for ObRequest representing a cancel order operation. """
    data: CancelOrderDataToSign     # The actual data that was signed
    signature: List[int]          # The signature over 'data' (serialized form) 