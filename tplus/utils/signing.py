import time

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.cancel_order import (  # For Cancel operations
    CancelOrder,
    CancelOrderRequest,
)
from tplus.utils.user import User

# LimitOrderDetails and Order are no longer needed for dummy cancel creation here


def create_cancel_order_ob_request_payload(
    signer: User, asset_identifier: AssetIdentifier, order_id: str
) -> CancelOrderRequest:
    """
    Creates the CancelOrderRequest payload for an ObRequest.
    This now only includes the order_id, matching the Rust struct.
    """
    cancel = CancelOrder(
        order_id=order_id, asset_identifier=asset_identifier, signer=signer.pubkey()
    )
    sign_payload_json = cancel.model_dump_json()
    compact_sign_payload_json = (
        sign_payload_json.replace(" ", "").replace("\r", "").replace("\n", "")
    )
    signature_bytes = signer.sign(compact_sign_payload_json)
    return CancelOrderRequest(
        cancel=cancel, signature=signature_bytes, post_sign_timestamp=time.time_ns()
    )
