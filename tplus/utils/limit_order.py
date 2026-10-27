import time
from typing import TYPE_CHECKING

from tplus.model.asset_identifier import AssetAddress, AssetIdentifier
from tplus.model.limit_order import GTC, GTD, IOC, LimitOrderDetails
from tplus.model.order import CreateOrderRequest, Order, Side, TradeTarget
from tplus.model.order_trigger import OrderTrigger
from tplus.model.sync_order import (
    SyncMakerOrderDetails,
    SyncSettlementTerms,
    SyncTakerOrderDetails,
    SyncTimeInForce,
)
from tplus.utils.user import User, to_user

if TYPE_CHECKING:
    from tplus.types import UserLike


def create_limit_order_ob_request_payload(
    quantity: int,
    price: int,
    side: str,
    signer: "UserLike",
    book_quantity_decimals: int,
    book_price_decimals: int,
    asset_identifier: AssetIdentifier,
    order_id: str,
    time_in_force: GTC | GTD | IOC | None = None,
    trigger: OrderTrigger | None = None,
    target: TradeTarget | None = None,
    reduce_only: bool = False,
    max_trading_fees_rate: int | None = None,
) -> CreateOrderRequest:
    signer = to_user(signer)
    side_normalized = Side.SELL if side.lower() == "sell" else Side.BUY

    actual_time_in_force = GTC(post_only=False) if time_in_force is None else time_in_force

    details = LimitOrderDetails(
        quantity=quantity,
        limit_price=price,
        time_in_force=actual_time_in_force,
    )
    actual_target = TradeTarget.margin_account_spot_trade() if target is None else target
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
        reduce_only=reduce_only,
        max_trading_fees_rate=(50000 if max_trading_fees_rate is None else max_trading_fees_rate),
    )
    sign_payload_json = order.signable_part()
    signature, additional_signers = signer.signing_parts(sign_payload_json)

    return CreateOrderRequest(
        order=order,
        signature=signature,
        post_sign_timestamp=time.time_ns(),
        additional_signers=additional_signers,
    )


def create_sync_taker_order_ob_request_payload(
    quantity: int,
    price: int,
    side: str,
    signer: "UserLike",
    book_quantity_decimals: int,
    book_price_decimals: int,
    asset_identifier: AssetIdentifier,
    order_id: str,
    base_token: AssetAddress,
    nonce: int,
    target: TradeTarget | None = None,
    max_trading_fees_rate: int | None = None,
) -> CreateOrderRequest:
    """Build and sign a sync taker: an IOC limit order routed across the sync book that
    would fill the most of it and the main book, walked together by price (main wins ties);
    the sync-book share settles on chain with that maker as settler. Sync liquidity is not
    taken first: execution can run main, then sync, then main again.

    ``base_token`` is the token of the market's base asset that moves on chain (address and
    chain); ``nonce`` is the vault settlement nonce of the signer's sub-account on that chain
    (``DepositVault.settlementCounts``). The trade must be a spot trade from the main
    account, which is the default target.
    """
    signer = to_user(signer)
    side_normalized = Side(side)
    details = SyncTakerOrderDetails(
        limit_price=price,
        quantity=quantity,
        settlement=SyncSettlementTerms(base_token=base_token, nonce=nonce),
    )
    order = Order(
        signer=signer.public_key,
        order_id=order_id,
        base_asset=asset_identifier,
        book_quantity_decimals=book_quantity_decimals,
        book_price_decimals=book_price_decimals,
        details=details,
        side=side_normalized,
        trigger=None,
        creation_timestamp_ns=time.time_ns(),
        target=TradeTarget.main_account_spot_trade() if target is None else target,
        reduce_only=False,
        max_trading_fees_rate=(50000 if max_trading_fees_rate is None else max_trading_fees_rate),
    )
    signature, additional_signers = signer.signing_parts(order.signable_part())
    return CreateOrderRequest(
        order=order,
        signature=signature,
        post_sign_timestamp=time.time_ns(),
        additional_signers=additional_signers,
    )


def create_sync_maker_order_ob_request_payload(
    quantity: int,
    price: int,
    side: str,
    signer: "UserLike",
    book_quantity_decimals: int,
    book_price_decimals: int,
    asset_identifier: AssetIdentifier,
    order_id: str,
    target: TradeTarget | None = None,
    time_in_force: SyncTimeInForce | None = None,
) -> CreateOrderRequest:
    """Build and sign a market maker's quote for its own sync book (GTC unless given)."""
    signer = to_user(signer)
    side_normalized = Side(side)
    details = SyncMakerOrderDetails(limit_price=price, quantity=quantity)
    if time_in_force is not None:
        details.time_in_force = time_in_force
    order = Order(
        signer=signer.public_key,
        order_id=order_id,
        base_asset=asset_identifier,
        book_quantity_decimals=book_quantity_decimals,
        book_price_decimals=book_price_decimals,
        details=details,
        side=side_normalized,
        trigger=None,
        creation_timestamp_ns=time.time_ns(),
        target=TradeTarget.margin_account_spot_trade() if target is None else target,
        reduce_only=False,
        max_trading_fees_rate=50000,
    )
    signature, additional_signers = signer.signing_parts(order.signable_part())
    return CreateOrderRequest(
        order=order,
        signature=signature,
        post_sign_timestamp=time.time_ns(),
        additional_signers=additional_signers,
    )


if __name__ == "__main__":
    order = create_limit_order_ob_request_payload(
        100, 50000, "Buy", User(), 3, 3, AssetIdentifier(root="200"), "zrhgiuzegf"
    )
    print(order.order.signable_part())
