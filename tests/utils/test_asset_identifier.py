from tplus.model.asset_identifier import AssetIdentifier


class TestAssetIdentifier:
    def test_address_chain_str_full_circle(self):
        addr = "0x0000000000000000000000000000000000000000"
        asset_str = f"{addr}@1"
        model = AssetIdentifier(asset_str)

        # Note: `mode_dump()` calls our custom model serializer.
        data = model.model_dump()

        expected = (
            "0000000000000000000000000000000000000000000000000000000000000000@0000000000000001"
        )
        assert data == expected

    def test_index_str_full_circle(self):
        model = AssetIdentifier(1)

        # Note: `mode_dump()` calls our custom model serializer.
        data = model.model_dump()

        expected = "1"
        assert data == expected

    def test_index_int_full_circle(self):
        model = AssetIdentifier("1")

        # Note: `mode_dump()` calls our custom model serializer.
        data = model.model_dump()

        expected = "1"
        assert data == expected

    def test_index_dict_full_circle(self):
        init_data = {"Index": 1}
        model = AssetIdentifier(init_data)
        data = model.model_dump()
        assert data == "1"

    def test_address_dict_full_circle(self):
        init_data = {
            "Address": {
                "address": [0] * 32,
                "chain": [1, 0, 0, 0, 0, 0, 0, 0],
            }
        }
        model = AssetIdentifier(init_data)
        data = model.model_dump()
        expected = (
            "0000000000000000000000000000000000000000000000000000000000000000@0100000000000000"
        )
        assert data == expected
