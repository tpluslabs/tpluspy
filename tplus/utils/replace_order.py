import time

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.order_trigger import TriggerAbove, TriggerBelow
from tplus.model.replace_order import ReplaceOrderDetails, ReplaceOrderRequestPayload
from tplus.utils.user import User


def create_replace_order_ob_request_payload(
    original_order_id: str,  # ID of the order to be replaced
    asset_identifier: AssetIdentifier,  # Asset ID of the order
    signer: User,
    # Complete effective terms the order will have once replaced (all mandatory).
    new_price: int,
    new_quantity: int,
    book_price_decimals: int,
    book_quantity_decimals: int,
    # Effective trigger state; None means the order has no trigger.
    new_trigger: TriggerAbove | TriggerBelow | None = None,
    # Timestamp for the replace operation itself
    request_timestamp_ns: int | None = None,
) -> ReplaceOrderRequestPayload:
    """
    Creates the ReplaceOrderRequestPayload for an ObRequest.
    This payload type directly corresponds to the Rust struct
    orderbook_messages::actions::ReplaceOrderRequest.

    The signed payload carries the **complete effective terms**, so ``new_price`` and
    ``new_quantity`` are mandatory: the server never fills an omitted term from its own view
    of the order. ``new_quantity`` is the lifetime-total quantity, not the remaining part.
    """

    current_ts = request_timestamp_ns if request_timestamp_ns is not None else time.time_ns()

    replace_details = ReplaceOrderDetails(
        order_id=original_order_id,
        base_asset=asset_identifier,
        timestamp_ns=current_ts,
        new_price_limit=new_price,
        new_quantity=new_quantity,
        new_trigger=new_trigger,
        book_price_decimals=book_price_decimals,
        book_quantity_decimals=book_quantity_decimals,
    )

    # Sign the ReplaceOrderDetails part
    # The Rust equivalent is ReplaceOrder::signable_part -> serde_json::to_string without spaces
    sign_payload_json = replace_details.model_dump_json(
        exclude_none=False
    )  # Ensure compact like server

    # Server does: payload.replace(" ", "").replace("\r", "").replace("\n", "") before signing
    # Pydantic's model_dump_json might not be compact enough by default for perfect match.
    # For exactness with Rust's specific string replacement for signing:
    compact_sign_payload_json = (
        sign_payload_json.replace(" ", "").replace("\r", "").replace("\n", "")
    )
    signature, additional_signers = signer.signing_parts(compact_sign_payload_json)
    if additional_signers:
        raise ValueError(
            "Order replacement does not support additional signers until its wire format "
            "can identify replacement co-signatures."
        )

    return ReplaceOrderRequestPayload(
        request=replace_details,
        user_id=signer.public_key,
        signature=signature,
        post_sign_timestamp=time.time_ns(),
    )
