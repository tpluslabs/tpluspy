import time

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.limit_order import GTC, GTD, IOC, LimitOrderDetails
from tplus.model.order import CreateOrderRequest, Order
from tplus.model.order_trigger import TriggerAbove, TriggerBelow
from tplus.utils.user import User


def create_limit_order_ob_request_payload(
    quantity: int,
    price: int,
    side: str,
    signer: User,
    book_quantity_decimals: int,
    book_price_decimals: int,
    asset_identifier: AssetIdentifier,
    order_id: str,
    time_in_force: GTC | GTD | IOC | None = None,
    trigger: TriggerAbove | TriggerBelow | None = None,
) -> CreateOrderRequest:
    side_normalized = "Sell" if side.lower() == "sell" else "Buy"

    actual_time_in_force = GTC(post_only=False) if time_in_force is None else time_in_force

    details = LimitOrderDetails(
        quantity=quantity,
        limit_price=price,
        time_in_force=actual_time_in_force,
    )
    order = Order(
        signer=list(bytes.fromhex(signer.public_key)),
        order_id=order_id,
        base_asset=asset_identifier,
        book_quantity_decimals=book_quantity_decimals,
        book_price_decimals=book_price_decimals,
        details=details,
        side=side_normalized,
        trigger=trigger,
        creation_timestamp_ns=time.time_ns(),
    )
    sign_payload_json = order.signable_part()
    signature_bytes = signer.sign(sign_payload_json)

    return CreateOrderRequest(
        order=order, signature=list(signature_bytes), post_sign_timestamp=time.time_ns()
    )


if __name__ == "__main__":
    order = create_limit_order_ob_request_payload(
        100, 50000, "Buy", User(), 3, 3, AssetIdentifier(root="200"), "zrhgiuzegf"
    )
    print(order.order.signable_part())
