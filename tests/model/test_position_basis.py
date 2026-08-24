from decimal import Decimal

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.position_basis import parse_position_basis


def test_parse_position_basis_preserves_decimal_strings_and_nullable_fields():
    rows = parse_position_basis(
        [
            {
                "sub_account": 0,
                "asset_id": "1",
                "domain": "spot",
                "side": None,
                "quantity": "1.500000000000000001",
                "cost": "225.00000000000000015",
                "entry_price": None,
                "avg_acquisition_price": "150.0000000000000001",
                "mark_price": "160.25",
                "unrealized_pnl": "15.37499999999999985",
            }
        ]
    )

    row = rows[0]
    assert row.asset_id == AssetIdentifier("1")
    assert row.domain == "spot"
    assert row.side is None
    assert row.quantity == Decimal("1.500000000000000001")
    assert row.cost == Decimal("225.00000000000000015")
    assert row.entry_price is None
    assert row.avg_acquisition_price == Decimal("150.0000000000000001")
    assert row.mark_price == Decimal("160.25")
    assert row.unrealized_pnl == Decimal("15.37499999999999985")


def test_parse_position_basis_parses_margin_side_and_entry_price():
    row = parse_position_basis(
        [
            {
                "sub_account": 1,
                "asset_id": "2",
                "domain": "margin",
                "side": "short",
                "quantity": "2",
                "cost": "300",
                "entry_price": "150",
                "avg_acquisition_price": None,
                "mark_price": None,
                "unrealized_pnl": None,
            }
        ]
    )[0]

    assert row.sub_account == 1
    assert row.domain == "margin"
    assert row.side == "short"
    assert row.entry_price == Decimal("150")
    assert row.avg_acquisition_price is None
