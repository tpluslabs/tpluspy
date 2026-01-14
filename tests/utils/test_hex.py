import pytest

from tplus.utils.hex import to_hex, to_vec


@pytest.mark.parametrize("value", [1, "0x01", "1", b"\x01"])
def test_to_vec(value):
    actual = to_vec(value)
    expected = [0, 1]
    assert actual == expected


def test_to_hex():
    integer = 1234
    actual_prefixed = to_hex(integer, prefix=False)
    assert actual_prefixed == "4d2"

    actual_unprefixed = to_hex(integer, prefix=True)
    assert actual_unprefixed == "0x4d2"
