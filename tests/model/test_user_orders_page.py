from tplus.model.order import parse_user_orders_page


def test_parse_user_orders_page_parses_envelope():
    page = parse_user_orders_page(
        {
            "orders": [],
            "page": 1,
            "limit": 2,
            "total_orders": 5,
            "total_pages": 3,
            "cursor_size": 2,
            "has_next_page": True,
            "next_page": 2,
        }
    )

    assert page.orders == []
    assert page.page == 1
    assert page.limit == 2
    assert page.total_orders == 5
    assert page.total_pages == 3
    assert page.cursor_size == 2
    assert page.has_next_page is True
    assert page.next_page == 2


def test_parse_user_orders_page_tolerates_bare_list():
    page = parse_user_orders_page([])

    assert page.orders == []
    assert page.total_orders == 0
    assert page.has_next_page is False
    assert page.page == 0


def test_parse_user_orders_page_tolerates_orders_only_envelope():
    page = parse_user_orders_page({"orders": []})

    assert page.orders == []
    assert page.total_orders == 0
    assert page.has_next_page is False


def test_user_orders_page_is_list_like():
    page = parse_user_orders_page([])

    assert len(page) == 0
    assert not page
    assert list(page) == []
    assert page[:] == []
