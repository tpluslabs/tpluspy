import time

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.market_order import MarketOrderDetails
from tplus.model.order import CreateOrderRequest, Order
from tplus.utils.user import User


def create_market_order_ob_request_payload(
    quantity: int,
    side: str,
    signer: User,
    book_quantity_decimals: int,
    asset_identifier: AssetIdentifier,
    order_id: str,
    fill_or_kill: bool = False,
) -> CreateOrderRequest:
    side_normalized = "Sell" if side.lower() == "sell" else "Buy"

    details = MarketOrderDetails(
        quantity=quantity, fill_or_kill=fill_or_kill, book_quantity_decimals=book_quantity_decimals
    )
    order = Order(
        signer=list(bytes.fromhex(signer.pubkey())),
        order_id=order_id,
        base_asset=asset_identifier,
        details=details,
        side=side_normalized,
        creation_timestamp_ns=time.time_ns(),
    )

    sign_payload_json = order.model_dump_json()
    signature_bytes = signer.sign(sign_payload_json)

    return CreateOrderRequest(order=order, signature=list(signature_bytes))
