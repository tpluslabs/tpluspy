from eth_pydantic_types.hex.bytes import HexBytes32

from tplus.model.chain_address import ChainAddress
from tplus.utils.domain import get_dstack_domain


def test_get_dstack_domain():
    address = "8800a71ad5201f7f3cc519a20c6cdf8c29297ea3000000000000000000000000"
    vault = ChainAddress.from_str(f"{address}@000000000000007a69")
    actual = get_dstack_domain(vault)

    # Same as what backend produces.
    expected = HexBytes32("2fb413e7c1cc1665bf930f80ab45477865105e67f74ffdb1a1ec3f6c05bff9a2")

    assert actual == expected, f"Expected {expected.hex()}, got {actual.hex()}"
