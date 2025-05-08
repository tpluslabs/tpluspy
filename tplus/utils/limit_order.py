import time
import uuid
from typing import Optional

from tplus.model.asset_identifier import IndexAsset
from tplus.model.limit_order import GTC, GTD, IOC, LimitOrderDetails
from tplus.model.order import CreateOrderRequest, Order
from tplus.model.signed_message import ObRequest, SignedMessage
from tplus.utils.user import User


def create_limit_order(
    quantity,
    price,
    side,
    signer: User,
    asset_index=200,
    order_id: Optional[str] = None,
    time_in_force: Optional[GTC | GTD | IOC] = None
):
    order_id = str(uuid.uuid4()) if order_id is None else order_id
    asset = IndexAsset(Index=asset_index)
    side = "Sell" if side.lower() == "sell" else "Buy"

    time_in_force = GTC(post_only=False) if time_in_force is None else time_in_force

    details = LimitOrderDetails(
        quantity=quantity, limit_price=price, time_in_force=time_in_force
    )
    order = Order(
        signer=list(bytes.fromhex(signer.pubkey())),
        order_id=order_id,
        base_asset=asset,
        details=details,
        side=side,
        creation_timestamp_ns=time.time_ns(),
    )

    sign_payload = order.model_dump_json()
    signature = signer.sign(sign_payload)
    create_order = CreateOrderRequest(order=order, signature=list(signature))
    request = ObRequest(
        order_id=order.order_id, base_asset=order.base_asset, ob_request_payload=create_order
    )
    message = SignedMessage(
        payload=request, user_id=signer.pubkey(), post_sign_timestamp=time.time_ns()
    )
    return message
