import json
import time
import uuid
from typing import Optional

from tplus.model.asset_identifier import IndexAsset
from tplus.model.market_order import MarketOrderDetails
from tplus.model.order import CreateOrderRequest, Order
from tplus.model.signed_message import ObRequest, SignedMessage
from tplus.utils.user import User


def create_market_order(quantity,
                        side,
                        signer: User,
                        fill_or_kill=False,
                        asset_index=200,
                        order_id: Optional[str] = None):
    order_id = str(uuid.uuid4()) if order_id is None else order_id
    asset = IndexAsset(asset_index)
    side = "Sell" if side.lower() == "sell" else "Buy"

    details = MarketOrderDetails(quantity=quantity, fill_or_kill=fill_or_kill)
    order = Order(signer=list(bytes.fromhex(signer.pubkey())), order_id=order_id, base_asset=asset, details=details, side=side,
                  creation_timestamp_ns=time.time_ns())

    sign_payload = json.dumps(order.to_dict())
    signature = signer.sign(sign_payload)
    create_order = CreateOrderRequest(order, signature=list(signature))
    request = ObRequest(order_id=order.order_id, base_asset=order.base_asset, ob_request_payload=create_order)
    message = SignedMessage(payload=request, user_id=signer.pubkey(), post_sign_timestamp=time.time_ns())
    return message
