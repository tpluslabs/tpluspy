from tplus.model.asset_identifier import AssetIdentifier


class TestAssetIdentifier:
    def test_address_chain_str_full_circle(self):
        addr = "0x0000000000000000000000000000000000000000"
        asset_str = f"{addr}@1"
        model = AssetIdentifier(asset_str)

        # Note: `mode_dump()` calls our custom model serializer.
        data = model.model_dump()

        expected = {
            "Address": {
                "address": [0] * 32,
                "chain": [1, 0, 0, 0, 0, 0, 0, 0],
            }
        }
        assert data == expected

    def test_index_str_full_circle(self):
        model = AssetIdentifier(1)

        # Note: `mode_dump()` calls our custom model serializer.
        data = model.model_dump()

        expected = {"Index": 1}
        assert data == expected

    def test_index_int_full_circle(self):
        model = AssetIdentifier("1")

        # Note: `mode_dump()` calls our custom model serializer.
        data = model.model_dump()

        expected = {"Index": 1}
        assert data == expected
