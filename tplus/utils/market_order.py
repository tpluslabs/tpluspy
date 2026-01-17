import time

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.market_order import (
    MarketBaseQuantity,
    MarketOrderDetails,
    MarketQuantity,
    MarketQuoteQuantity,
)
from tplus.model.order import CreateOrderRequest, Order, Side, TradeTarget
from tplus.model.order_trigger import TriggerAbove, TriggerBelow
from tplus.utils.user import User


def create_market_order_ob_request_payload(
    side: str,
    signer: User,
    book_quantity_decimals: int,
    book_price_decimals: int,
    asset_identifier: AssetIdentifier,
    order_id: str,
    base_quantity: MarketBaseQuantity | None = None,
    quote_quantity: MarketQuoteQuantity | None = None,
    fill_or_kill: bool = False,
    trigger: TriggerAbove | TriggerBelow | None = None,
    target: TradeTarget | None = None,
) -> CreateOrderRequest:
    side_normalized = Side.SELL if side.lower() == "sell" else Side.BUY

    details = MarketOrderDetails(
        quantity=MarketQuantity(base_asset=base_quantity, quote_asset=quote_quantity),
        fill_or_kill=fill_or_kill,
    )
    actual_target = TradeTarget.margin_spot() if target is None else target
    order = Order(
        signer=signer.public_key,
        order_id=order_id,
        base_asset=asset_identifier,
        book_quantity_decimals=book_quantity_decimals,
        book_price_decimals=book_price_decimals,
        details=details,
        side=side_normalized,
        trigger=trigger,
        creation_timestamp_ns=time.time_ns(),
        target=actual_target,
    )

    sign_payload_json = order.signable_part()
    signature_bytes = signer.sign(sign_payload_json)

    return CreateOrderRequest(
        order=order, signature=list(signature_bytes), post_sign_timestamp=time.time_ns()
    )
