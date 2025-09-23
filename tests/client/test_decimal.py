from tplus.client.clearingengine.decimal import _prep_request
from tplus.model.asset_identifier import AssetIdentifier


def test_prep_request():
    assets = [
        "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    ]
    chain = 42161
    actual = _prep_request(
        assets,
        chain,
    )
    expected = {"assets": assets, "chains": [chain]}
    assert actual == expected


def test_prep_request_given_asset_ids():
    assets = [
        AssetIdentifier("0x82aF49447D8a07e3bd95BD0d56f35241523fBab1@000000000000a4b1"),
        AssetIdentifier("0xaf88d065e77c8cC2239327C5EDb3A432268e5831@000000000000a4b1"),
    ]
    chain = 42161
    actual = _prep_request(
        assets,
        chain,
    )
    expected = {"assets": [a.model_dump() for a in assets], "chains": [chain]}
    assert actual == expected
