import time
from typing import Union  # Import Union

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.cancel_order import (  # For Cancel operations
    CancelOrderRequest,
)
from tplus.model.order import CreateOrderRequest  # For Create operations
from tplus.model.replace_order import ReplaceOrderRequestPayload  # For Replace operations
from tplus.model.signed_message import ObRequest, SignedMessage
from tplus.utils.user import User

# LimitOrderDetails and Order are no longer needed for dummy cancel creation here


def create_cancel_order_ob_request_payload(
    order_id: str
) -> CancelOrderRequest:
    """
    Creates the CancelOrderRequest payload for an ObRequest.
    This now only includes the order_id, matching the Rust struct.
    """
    return CancelOrderRequest(order_id=order_id)


def build_signed_message(
    order_id: str,
    asset_identifier: AssetIdentifier,
    # This payload can now be either for a create or a cancel operation
    operation_specific_payload: Union[CreateOrderRequest, CancelOrderRequest, ReplaceOrderRequestPayload],
    signer: User
) -> SignedMessage:
    """
    Builds the common ObRequest and SignedMessage wrappers around an
    operation-specific payload (CreateOrderRequest or CancelOrderRequest).

    Args:
        order_id: The order ID.
        asset_identifier: The asset identifier.
        operation_specific_payload: The payload for the request (e.g., a signed limit order,
                                    or a signed cancel request).
        signer: The user performing the action.

    Returns:
        A fully constructed SignedMessage.
    """
    request_wrapper = ObRequest(
        order_id=order_id,
        base_asset=asset_identifier,
        ob_request_payload=operation_specific_payload
    )

    message = SignedMessage(
        payload=request_wrapper,
        user_id=signer.pubkey(), # This is the key for user identification on the SignedMessage wrapper
        post_sign_timestamp=time.time_ns()
    )
    return message
