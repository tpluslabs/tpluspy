import pytest

from tplus.model.asset_identifier import AssetIdentifier, ChainAddress


class TestChainAddress:
    @pytest.fixture(scope="class")
    def chain_address(self):
        return ChainAddress(root="62622E77D1349Face943C6e7D5c01C61465FE1dc@a4b1")

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
        assert chain_address.chain_id == 42161


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
            "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@000000000000a4b1"
        )
        asset_id = AssetIdentifier(raw_str)
        actual = asset_id.model_dump()
        assert actual == raw_str

    def test_address_str_unpadded_address(self):
        """
        Shows it automatically pads and utilizes an asset address str.
        """
        raw_str = "62622E77D1349Face943C6e7D5c01C61465FE1dc@000000000000a4b1"
        asset_id = AssetIdentifier(raw_str)
        actual = asset_id.model_dump()
        expected = (
            "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@000000000000a4b1"
        )
        assert actual == expected

    def test_address_str_unpadded_chain(self):
        """
        Shows it automatically pads and utilizes an asset address str.
        """
        raw_str = "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@a4b1"
        asset_id = AssetIdentifier(raw_str)
        actual = asset_id.model_dump()
        expected = (
            "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@000000000000a4b1"
        )
        assert actual == expected

    def test_address_decimal_chain(self):
        """
        Shows it automatically pads and utilizes an asset address str.
        """
        raw_str = "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@42161"
        asset_id = AssetIdentifier(raw_str)
        actual = asset_id.model_dump()
        expected = (
            "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@000000000000a4b1"
        )
        assert actual == expected

    def test_address_decimal_chain_and_unpadded_address(self):
        """
        Shows it automatically pads and utilizes an asset address str.
        """
        raw_str = "62622e77d1349face943c6e7d5c01c61465fe1dc@42161"
        asset_id = AssetIdentifier(raw_str)
        actual = asset_id.model_dump()
        expected = (
            "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@000000000000a4b1"
        )
        assert actual == expected

    def test_address_str_unpadded_both_sides(self):
        """
        Shows it automatically pads and utilizes an asset address str.
        """
        raw_str = "62622E77D1349Face943C6e7D5c01C61465FE1dc@a4b1"
        asset_id = AssetIdentifier(raw_str)
        actual = asset_id.model_dump()
        expected = (
            "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@000000000000a4b1"
        )
        assert actual == expected
