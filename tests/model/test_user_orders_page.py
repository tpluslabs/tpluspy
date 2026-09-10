from tplus.model.order import parse_user_orders_page


def _historical_order() -> dict:
    return {
        "order_id": "order-1",
        "base_asset": "1",
        "account_index": 1,
        "is_spot": False,
        "side": "Buy",
        "limit_price": "100.5",
        "quantity": "2",
        "amount": None,
        "confirmed_filled_quantity": "1",
        "confirmed_filled_amount": "100.5",
        "confirmed_trading_fees_amount": "0.1",
        "good_until_timestamp_ns": None,
        "timestamp_ns": 10,
        "is_immediate_or_cancel": False,
        "is_fill_or_kill": False,
        "is_liquidation": False,
        "is_auto_deleverage": False,
        "is_reduce_only": False,
        "canceled": False,
        "status": "Completed",
        "trigger_above_price": None,
        "trigger_below_price": None,
        "trigger_touched": None,
        "trigger_enabled_quantity": None,
        "parent_id": None,
        "last_update_timestamp_ns": 20,
    }


def test_parse_user_orders_page_parses_envelope():
    page = parse_user_orders_page(
        {
            "orders": [],
            "has_next_page": True,
            "next_page": 2,
        }
    )

    assert page.orders == []
    assert page.has_next_page is True
    assert page.next_page == 2


def test_parse_user_orders_page_accepts_compact_history_shape():
    page = parse_user_orders_page({"orders": [_historical_order()]})

    assert len(page) == 1
    assert page[0].order_id == "order-1"
    assert page[0].confirmed_filled_quantity == 1


def test_parse_user_orders_page_tolerates_bare_list():
    page = parse_user_orders_page([])

    assert page.orders == []
    assert page.has_next_page is False


def test_parse_user_orders_page_tolerates_orders_only_envelope():
    page = parse_user_orders_page({"orders": []})

    assert page.orders == []
    assert page.has_next_page is False


def test_user_orders_page_is_list_like():
    page = parse_user_orders_page([])

    assert len(page) == 0
    assert not page
    assert list(page) == []
    assert page[:] == []
