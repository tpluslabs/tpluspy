from decimal import Decimal

from tplus.model.position import PositionResponse, parse_positions_page


def _position(sub_account_index: int, name: str) -> dict:
    return {
        "asset_id": "1",
        "sub_account_index": sub_account_index,
        "name": name,
        "side": "long",
        "size": "1.5",
        "entry_price": "100",
        "mark_price": "101",
        "unrealized_pnl": "1.5",
        "margin": "10",
        "leverage": "4",
        "liquidation_price": "90",
        "base_credits": "1.5",
        "base_liabilities": "0",
        "quote_credits": "0",
        "quote_liabilities": "150",
    }


def test_position_response_parses_optional_fields_as_none():
    pos = PositionResponse.model_validate(
        {
            "asset_id": "1",
            "sub_account_index": 1,
            "name": "Margin",
            "side": "short",
            "size": "2",
            "base_credits": "0",
            "base_liabilities": "2",
            "quote_credits": "200",
            "quote_liabilities": "0",
        }
    )
    assert pos.side == "short"
    assert pos.size == Decimal("2")
    assert pos.entry_price is None
    assert pos.liquidation_price is None


def test_parse_positions_page_parses_envelope():
    page = parse_positions_page(
        {
            "positions": [_position(1, "Margin"), _position(2, "Iso")],
            "page": 0,
            "limit": 1,
            "total_positions": 2,
            "total_pages": 2,
            "cursor_size": 1,
            "has_next_page": True,
            "next_page": 1,
        }
    )
    assert [p.name for p in page.positions] == ["Margin", "Iso"]
    assert page.total_positions == 2
    assert page.has_next_page is True


def test_parse_positions_page_tolerates_bare_list():
    page = parse_positions_page([_position(1, "Margin")])
    assert page.total_positions == 1
    assert page.has_next_page is False
    assert page.next_page is None
