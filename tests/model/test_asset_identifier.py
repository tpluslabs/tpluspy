import pytest

from tplus.model.asset_identifier import AssetIdentifier, ChainAddress


class TestChainAddress:
    @pytest.fixture(scope="class")
    def chain_address(self):
        return ChainAddress(root="62622E77D1349Face943C6e7D5c01C61465FE1dc@000000000000aa36a7")

    def test_address(self, chain_address):
        assert (
            chain_address.address
            == "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000"
        )

    def test_evm_address(self, chain_address):
        """
        Evm address should be 20 bytes and checksummed.
        """
        assert chain_address.evm_address == "0x62622E77D1349Face943C6e7D5c01C61465FE1dc"

    def test_chain_id(self, chain_address):
        assert chain_address.chain_id.vm_id == 11155111


class TestAssetIdentifier:
    def test_index_str(self):
        asset_id = AssetIdentifier("0")
        actual = f"{asset_id}"
        assert actual == "0"

    def test_address_str(self):
        """
        Shows it automatically pads and utilizes an asset address str.
        """
        raw_str = (
            "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@00000000000000a4b1"
        )
        asset_id = AssetIdentifier(raw_str)
        actual = asset_id.model_dump()
        assert actual == raw_str

    def test_address_str_unpadded_address(self):
        """
        Shows it automatically pads and utilizes an asset address str.
        """
        raw_str = "62622E77D1349Face943C6e7D5c01C61465FE1dc@00000000000000a4b1"
        asset_id = AssetIdentifier(raw_str)
        actual = asset_id.model_dump()
        expected = (
            "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@00000000000000a4b1"
        )
        assert actual == expected

    def test_address_str_unpadded_chain(self):
        """
        Shows it automatically pads and utilizes an asset address str.
        """
        raw_str = (
            "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@00000000000000a4b1"
        )
        asset_id = AssetIdentifier(raw_str)
        actual = asset_id.model_dump()
        expected = (
            "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@00000000000000a4b1"
        )
        assert actual == expected

    def test_address_str_unpadded_both_sides(self):
        """
        Shows it automatically pads and utilizes an asset address str.
        """
        raw_str = "62622E77D1349Face943C6e7D5c01C61465FE1dc@00000000000000a4b1"
        asset_id = AssetIdentifier(raw_str)
        actual = asset_id.model_dump()
        expected = (
            "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@00000000000000a4b1"
        )
        assert actual == expected

    def test_address_chain_str_full_circle(self):
        addr = "0x0000000000000000000000000000000000000000"
        asset_str = f"{addr}@000000000000000001"
        model = AssetIdentifier(asset_str)

        # Note: `mode_dump()` calls our custom model serializer.
        data = model.model_dump()

        expected = (
            "0000000000000000000000000000000000000000000000000000000000000000@000000000000000001"
        )
        assert data == expected

    def test_index_str_full_circle(self):
        model = AssetIdentifier("1")

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
        model = AssetIdentifier.model_validate(init_data)
        data = model.model_dump()
        assert data == "1"

    def test_address_dict_full_circle(self):
        init_data = {
            "Address": {
                "address": [0] * 32,
                "chain": [0, 0, 0, 0, 0, 0, 0, 1],
            }
        }
        model = AssetIdentifier.model_validate(init_data)
        data = model.model_dump()
        expected = (
            "0000000000000000000000000000000000000000000000000000000000000000@0000000000000001"
        )
        assert data == expected

    def test_address_str_missing_chain_raises(self):
        with pytest.raises(ValueError):
            AssetIdentifier("0x62622E77D1349Face943C6e7D5c01C61465FE1dc")

    def test_word_string_raises(self):
        with pytest.raises(ValueError):
            AssetIdentifier("TestToken")

    def test_contains(self):
        addr = "62622E77D1349Face943C6e7D5c01C61465FE1dc"
        long_addr = f"{addr}000000000000000000000000"
        asset_id = AssetIdentifier(f"{addr}@00000000000000a4b1")
        assert addr in asset_id
        assert bytes.fromhex(addr) in asset_id
        assert long_addr in asset_id
        assert bytes.fromhex(long_addr) in asset_id

    def test_chain_id_too_small(self):
        raw_str = "62622E77D1349Face943C6e7D5c01C61465FE1dc@a4b1"
        with pytest.raises(ValueError):
            _ = AssetIdentifier(raw_str)
