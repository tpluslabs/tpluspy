from tplus.model.asset_identifier import AssetIdentifier


class TestAssetIdentifier:
    def test_str(self):
        asset_id = AssetIdentifier("0")
        actual = f"{asset_id}"
        assert actual == "0"
