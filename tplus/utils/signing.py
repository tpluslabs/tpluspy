import time
from typing import Union # Import Union

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.order import CreateOrderRequest # For Create operations
from tplus.model.cancel_order import CancelOrderDataToSign, CancelOrderRequest # For Cancel operations
from tplus.model.signed_message import ObRequest, SignedMessage
from tplus.utils.user import User
# LimitOrderDetails and Order are no longer needed for dummy cancel creation here


def create_cancel_order_ob_request_payload(
    order_id: str, 
    asset_identifier: AssetIdentifier,
    signer: User
) -> CancelOrderRequest:
    """
    Creates the CancelOrderRequest payload for an ObRequest.
    This involves creating the data to be signed, signing it, and packaging it.

    Args:
        order_id: The ID of the order to be cancelled.
        asset_identifier: The asset identifier for the order.
        signer: The user performing the cancellation.

    Returns:
        A CancelOrderRequest object containing the signed cancellation data.
    """
    user_pubkey = signer.pubkey()
    cancel_data_to_sign = CancelOrderDataToSign(
        order_id=order_id,
        asset_identifier=asset_identifier, # Assuming AssetIdentifier itself can be part of the signed payload
                                        # If only string form is needed, adjust AssetIdentifier or use asset_identifier.value
        user_id=user_pubkey, # Explicitly including user_id in the signed payload
        cancel_timestamp_ns=time.time_ns()
    )

    # Serialize the data to be signed (Pydantic's model_dump_json is a good choice)
    sign_payload_json = cancel_data_to_sign.model_dump_json()
    signature_bytes = signer.sign(sign_payload_json)
    
    return CancelOrderRequest(
        data=cancel_data_to_sign,
        signature=list(signature_bytes)
    )


def build_signed_message(
    order_id: str,
    asset_identifier: AssetIdentifier,
    # This payload can now be either for a create or a cancel operation
    operation_specific_payload: Union[CreateOrderRequest, CancelOrderRequest], 
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