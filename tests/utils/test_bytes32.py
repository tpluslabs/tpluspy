from tplus.utils.bytes32 import to_bytes32


def test_to_bytes32():
    address = "0x0000000000000000000000000000000000000001"
    actual = to_bytes32(address)

    # Right pads by default.
    expected = bytes.fromhex("0000000000000000000000000000000000000001000000000000000000000000")
    assert actual == expected


def test_to_bytes32_left_pad():
    address = "0x0000000000000000000000000000000000000001"
    actual = to_bytes32(address, pad="left")

    # Right pads by default.
    expected = bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000001")
    assert actual == expected


def test_to_bytes32_no_prefix():
    address = "0000000000000000000000000000000000000001"
    actual = to_bytes32(address)

    # Right pads by default.
    expected = bytes.fromhex("0000000000000000000000000000000000000001000000000000000000000000")
    assert actual == expected
