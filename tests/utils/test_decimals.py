import pytest

from tplus.constants import CLEARING_ENGINE_DECIMALS
from tplus.utils.decimals import (
    normalize_decimals,
    normalize_from_inventory,
    normalize_to_inventory,
)


def test_normalize_decimals_equal():
    assert normalize_decimals(12345, 6, 6, "down") == 12345
    assert normalize_decimals(12345, 6, 6, "down") == 12345


def test_normalize_decimals_scale_up():
    # from 6 decimals to 18 decimals
    amount = 12345
    result = normalize_decimals(amount, 6, 18, "down")
    assert result == amount * 10**12


def test_normalize_decimals_scale_down_round_down():
    # from 18 decimals to 6 decimals, round down
    amount = 123456789000000000000  # 123.456789 tokens at 18 decimals
    result = normalize_decimals(amount, 18, 6, "down")
    assert result == amount // 10**12


def test_normalize_decimals_scale_down_round_up():
    # from 18 decimals to 6 decimals, round up
    amount = 123456789000000000001  # just slightly above
    result = normalize_decimals(amount, 18, 6, "up")
    expected = (amount + (10**12 - 1)) // 10**12
    assert result == expected
    # Verify it's strictly greater than floor division
    assert result == amount // 10**12 + 1


def test_normalize_to_inventory_matches_manual():
    amount = 1000
    decimals = 6
    result = normalize_to_inventory(amount, decimals, "down")
    expected = normalize_decimals(amount, decimals, CLEARING_ENGINE_DECIMALS, "down")
    assert result == expected


def test_normalize_from_inventory_matches_manual():
    amount = 10**18  # 1.0 in 18-decimal units
    decimals = 6
    result = normalize_from_inventory(amount, decimals, "down")
    expected = normalize_decimals(amount, CLEARING_ENGINE_DECIMALS, decimals, "down")
    assert result == expected


@pytest.mark.parametrize("rounding", ["down", "up"])
def test_roundtrip_invertible(rounding):
    """
    Converting to inventory and back should give the same result
    if decimals <= INVENTORY_DECIMALS and round_down=True.
    """
    amount = 987654321
    decimals = 6
    to_inventory = normalize_to_inventory(amount, decimals, rounding)
    back = normalize_from_inventory(to_inventory, decimals, rounding)

    if rounding == "down":
        assert back == amount
    else:
        # Rounding up can overshoot slightly
        assert back >= amount
