from tplus.asset_metadata import asset_label, asset_metadata_dict, get_asset_metadata
from tplus.model.asset_identifier import AssetIdentifier


def test_resolves_index_asset_metadata():
    metadata = get_asset_metadata("1")

    assert metadata is not None
    assert metadata.symbol == "ETH"
    assert metadata.asset_class == "ETH"
    assert metadata.representations == ("WETH",)


def test_resolves_chain_address_alias_metadata():
    asset = AssetIdentifier("0xaf88d065e77c8cc2239327c5edb3a432268e5831@00000000000000a4b1")

    assert asset_metadata_dict(asset) == {
        "index": 0,
        "symbol": "USDC",
        "asset_class": "USD",
        "representations": ["USDC", "USDT"],
    }


def test_unknown_asset_label_does_not_guess_symbol():
    assert get_asset_metadata("999") is None
    assert asset_label("999") == "asset 999"
