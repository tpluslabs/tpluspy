from tplus.client.oms.assetregistry import _prep_request
from tplus.model.asset_identifier import AssetAddress, AssetIdentifier

CHAIN_ID = "00000000000000a4b1"
ASSET_1_ADDRESS = "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1"
ASSET_2_ADDRESS = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
ASSET_1_CHAINADDRESS = f"82af49447d8a07e3bd95bd0d56f35241523fbab1{'0' * 24}@{CHAIN_ID}"
ASSET_2_CHAINADDRESS = f"af88d065e77c8cc2239327c5edb3a432268e5831{'0' * 24}@{CHAIN_ID}"


def test_prep_request_mixed_input_types():
    assets: list[str | AssetAddress] = [
        f"{ASSET_1_ADDRESS}@{CHAIN_ID}",
        AssetIdentifier(f"{ASSET_2_ADDRESS}@{CHAIN_ID}"),
    ]
    actual = _prep_request(assets)
    assert actual == {"assets": [ASSET_1_CHAINADDRESS, ASSET_2_CHAINADDRESS]}
