import pytest

from tplus.utils.address import to_evm_address


@pytest.mark.parametrize(
    "address,expected",
    (
        pytest.param(
            "62622E77D1349Face943C6e7D5c01C61465FE1dc000000000000000000000000",
            "0x62622E77D1349Face943C6e7D5c01C61465FE1dc",
            id="left-aligned-32-bytes",
        ),
        pytest.param(
            "0x62622E77D1349Face943C6e7D5c01C61465FE1dc",
            "0x62622E77D1349Face943C6e7D5c01C61465FE1dc",
            id="20-bytes",
        ),
        pytest.param(
            "0x02c84e944F97F4A4f60221e6fb5d5DbAE49c7aaB",
            "0x02c84e944F97F4A4f60221e6fb5d5DbAE49c7aaB",
            id="leading-zero",
        ),
        pytest.param(
            "00c84e944f97f4a4f60221e6fb5d5dbae49c7aab000000000000000000000000",
            "0x00C84E944f97F4a4f60221e6Fb5d5dbAE49c7aAb",
            id="leading-zero-byte-left-aligned",
        ),
        pytest.param(
            "0x0000000000000000000000000000000000000001",
            "0x0000000000000000000000000000000000000001",
            id="mostly-zeros",
        ),
    ),
)
def test_to_evm_address(address, expected):
    assert to_evm_address(address) == expected


@pytest.mark.parametrize(
    "address",
    (
        pytest.param("ab" * 19, id="short"),
        pytest.param("ab" * 32, id="no-leading-zero"),
        pytest.param("0" + "ab" * 31 + "c", id="leading-zero"),
        pytest.param("00" + "ab" * 31, id="leading-zero-byte"),
        pytest.param("02" + "ab" * 31, id="leading-02"),
    ),
)
def test_to_evm_address_rejects_non_evm_address(address):
    with pytest.raises(ValueError, match="not an EVM address"):
        to_evm_address(address)
