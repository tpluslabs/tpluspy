import pytest

from tplus.utils.address import to_evm_address


@pytest.mark.parametrize(
    "address",
    (
        "62622E77D1349Face943C6e7D5c01C61465FE1dc000000000000000000000000",
        "0x62622E77D1349Face943C6e7D5c01C61465FE1dc",
    ),
)
def test_to_evm_address(address):
    actual = to_evm_address(address)
    expected = "0x62622E77D1349Face943C6e7D5c01C61465FE1dc"
    assert actual == expected
