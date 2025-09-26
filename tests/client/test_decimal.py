from tplus.client.clearingengine.decimal import _prep_request
from tplus.model.asset_identifier import AssetIdentifier

ASSET_1_ADDRESS = "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1"
ASSET_2_ADDRESS = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
CHAIN = 42161
ASSET_1_CHAINADDRESS = (
    "82af49447d8a07e3bd95bd0d56f35241523fbab1000000000000000000000000@000000000000a4b1"
)
ASSET_2_CHAINADDRESS = (
    "af88d065e77c8cc2239327c5edb3a432268e5831000000000000000000000000@000000000000a4b1"
)


def test_prep_request():
    assets = [ASSET_1_ADDRESS, ASSET_2_ADDRESS]
    actual = _prep_request(
        assets,
        CHAIN,
    )
    expected = {"assets": [ASSET_1_CHAINADDRESS, ASSET_2_CHAINADDRESS], "chains": [CHAIN]}
    assert actual == expected


def test_prep_request_given_asset_ids():
    assets: list[AssetIdentifier | str] = [
        AssetIdentifier("0x82aF49447D8a07e3bd95BD0d56f35241523fBab1@000000000000a4b1"),
        AssetIdentifier("0xaf88d065e77c8cC2239327C5EDb3A432268e5831@000000000000a4b1"),
    ]
    chain = 42161
    actual = _prep_request(
        assets,
        chain,
    )
    expected = {"assets": [ASSET_1_CHAINADDRESS, ASSET_2_CHAINADDRESS], "chains": [chain]}
    assert actual == expected
