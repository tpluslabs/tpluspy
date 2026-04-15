"""
Close-all preview response from OMS GET /positions/close-all/{user_id}/{sub_account}.
"""

from decimal import Decimal

from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.order import Side


class UnsignedCloseOrder(BaseModel):
    """Unsigned limit order payload for closing a margin position (client signs and batch-submits)."""

    asset_id: AssetIdentifier
    side: Side
    quantity: int
    suggested_max_sellable_amount: int | None = None
    oracle_price: Decimal | None = None
    book_price_decimals: int
    book_quantity_decimals: int
    sub_account_index: int
    reduce_only: bool


class CloseAllPreviewResponse(BaseModel):
    orders: list[UnsignedCloseOrder]
    errors: dict[str, str]


def parse_unsigned_close_order(data: dict) -> UnsignedCloseOrder:
    return UnsignedCloseOrder(
        asset_id=AssetIdentifier.model_validate(data["asset_id"]),
        side=Side(data["side"]),
        quantity=int(data["quantity"]),
        suggested_max_sellable_amount=(
            int(data["suggested_max_sellable_amount"])
            if data.get("suggested_max_sellable_amount") is not None
            else None
        ),
        oracle_price=Decimal(data["oracle_price"]),
        book_price_decimals=int(data["book_price_decimals"]),
        book_quantity_decimals=int(data["book_quantity_decimals"]),
        sub_account_index=int(data["sub_account_index"]),
        reduce_only=bool(data["reduce_only"]),
    )


def parse_close_all_preview(data: dict) -> CloseAllPreviewResponse:
    orders = [parse_unsigned_close_order(o) for o in data.get("orders", [])]
    errors = data.get("errors", {})
    return CloseAllPreviewResponse(orders=orders, errors=errors)
