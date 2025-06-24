import pytest

from tplus.utils.hex import to_vec


@pytest.mark.parametrize("value", [1, "0x01", "1", b"\x01"])
def test_vec(value):
    actual = to_vec(value)
    expected = [0, 1]
    assert actual == expected
