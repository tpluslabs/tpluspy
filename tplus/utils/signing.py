import time
from typing import TYPE_CHECKING

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.cancel_order import CancelOrder, CancelOrderRequest
from tplus.utils.user import to_user

if TYPE_CHECKING:
    from tplus.types import UserLike


def create_cancel_order_ob_request_payload(
    signer: "UserLike", asset_identifier: AssetIdentifier, order_id: str
) -> CancelOrderRequest:
    """Creates the CancelOrderRequest payload for an ObRequest."""
    signer = to_user(signer)
    cancel = CancelOrder(order_id=order_id, asset_id=asset_identifier, signer=signer.public_key)
    return CancelOrderRequest(cancel=cancel, post_sign_timestamp=time.time_ns())
