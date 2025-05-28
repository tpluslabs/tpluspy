import time
from typing import Optional

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.replace_order import ReplaceOrderDetails, ReplaceOrderRequestPayload
from tplus.utils.user import User


def create_replace_order_ob_request_payload(
    original_order_id: str,  # ID of the order to be replaced
    asset_identifier: AssetIdentifier,  # Asset ID of the order
    signer: User,
    # New parameters for the order
    new_price: Optional[int] = None,
    new_quantity: Optional[int] = None,
    # Market details, may be needed if not replacing price/qty or if server requires them
    book_price_decimals: Optional[int] = None,
    book_quantity_decimals: Optional[int] = None,
    # Timestamp for the replace operation itself
    request_timestamp_ns: Optional[int] = None,
) -> ReplaceOrderRequestPayload:
    """
    Creates the ReplaceOrderRequestPayload for an ObRequest.
    This payload type directly corresponds to the Rust struct
    orderbook_messages::actions::ReplaceOrderRequest.
    """

    current_ts = request_timestamp_ns if request_timestamp_ns is not None else time.time_ns()

    replace_details = ReplaceOrderDetails(
        order_id=original_order_id,
        timestamp_ns=current_ts,
        new_price_limit=new_price,
        new_quantity=new_quantity,
        book_price_decimals=book_price_decimals,
        book_quantity_decimals=book_quantity_decimals,
    )

    # Sign the ReplaceOrderDetails part
    # The Rust equivalent is ReplaceOrder::signable_part -> serde_json::to_string without spaces
    sign_payload_json = replace_details.model_dump_json(
        exclude_none=True
    )  # Ensure compact like server

    # Server does: payload.replace(" ", "").replace("\r", "").replace("\n", "") before signing
    # Pydantic's model_dump_json might not be compact enough by default for perfect match.
    # For exactness with Rust's specific string replacement for signing:
    compact_sign_payload_json = (
        sign_payload_json.replace(" ", "").replace("\r", "").replace("\n", "")
    )
    signature_bytes = signer.sign(compact_sign_payload_json)

    return ReplaceOrderRequestPayload(
        request=replace_details,
        user_id=signer.pubkey(),
        asset_id=asset_identifier,
        signature=list(signature_bytes),
    )
