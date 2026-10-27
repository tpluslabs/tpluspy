import time
from typing import Any

from tplus.model.asset_identifier import AssetIdentifier


def create_amend_order_ob_request_payload(
    order_id: str,
    asset_identifier: AssetIdentifier,
    user_id: str,
    new_quantity: int,
    book_quantity_decimals: int,
    expected_authorization_revision: int | None = None,
    request_timestamp_ns: int | None = None,
) -> dict[str, Any]:
    """
    Creates the payload of an amend, as ``PATCH /orders/amend`` and ``PATCH
    /orders/batch-amend`` take it. Corresponds to the Rust struct
    orderbook_messages::actions::AmendOrderRequest.

    An amend carries no signature: the OMS fills in its operator key and receive time,
    and treats every amend it receives from a user as user-initiated.
    """
    return {
        "request": {
            "order_id": order_id,
            "base_asset": asset_identifier.model_dump()
            if hasattr(asset_identifier, "model_dump")
            else asset_identifier,
            "new_quantity": new_quantity,
            "book_quantity_decimals": book_quantity_decimals,
            "expected_authorization_revision": expected_authorization_revision,
            "timestamp_ns": request_timestamp_ns
            if request_timestamp_ns is not None
            else time.time_ns(),
            "source": "User",
        },
        "user_id": user_id,
        "target": {"account": 0, "is_spot": False},
        "oms_operator_pubkey": "",
        "receive_timestamp_ns": None,
    }
