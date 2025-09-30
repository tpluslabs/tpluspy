import pytest

from tplus.utils.address import public_key_to_address


@pytest.fixture(scope="module")
def public_key_hex():
    return "ead3ca781763c5fc540f6369548afd020d25e87d73be345a158e6d523d3442ac"


def test_public_key_to_address(public_key_hex):
    expected = "0x792f28E43A8ca0361C9aD39fa6eFfe368493D24F"
    actual = public_key_to_address(public_key_hex)
    assert actual == expected

    # Show it still works with a prefix.
    prefixed_pubkey = f"02{public_key_hex}"
    actual = public_key_to_address(prefixed_pubkey)
    assert actual == expected

    # Show it works when given bytes.
    actual = public_key_to_address(bytes.fromhex(public_key_hex))
    assert actual == expected

    # Show it works when given bytes w/ a prefix.
    actual = public_key_to_address(bytes.fromhex(prefixed_pubkey))
    assert actual == expected
