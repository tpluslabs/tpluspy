from decimal import Decimal

from tplus.model.close_all_positions_preview import parse_close_all_preview
from tplus.model.order import Side


def _close_order(**overrides: object) -> dict:
    order = {
        "asset_id": "2",
        "side": "Buy",
        "quantity": 48808,
        "suggested_max_sellable_amount": 1234,
        "oracle_price": "79882.74",
        "book_price_decimals": 1,
        "book_quantity_decimals": 5,
        "sub_account_index": 1,
        "reduce_only": True,
    }
    order.update(overrides)
    return order


def test_close_all_preview_parses_oracle_price():
    preview = parse_close_all_preview({"orders": [_close_order()], "errors": {}})

    (order,) = preview.orders
    assert order.side is Side.BUY
    assert order.quantity == 48808
    assert order.oracle_price == Decimal("79882.74")


def test_close_all_preview_accepts_missing_oracle_price():
    # Prod OMS returns oracle_price: null for assets without a live oracle
    # reading; the parser must not turn that into TypeError.
    preview = parse_close_all_preview(
        {
            "orders": [
                _close_order(oracle_price=None),
                {k: v for k, v in _close_order(asset_id="3").items() if k != "oracle_price"},
            ],
            "errors": {"4": "no position"},
        }
    )

    assert [order.oracle_price for order in preview.orders] == [None, None]
    assert [str(order.asset_id) for order in preview.orders] == ["2", "3"]
    assert preview.errors == {"4": "no position"}
