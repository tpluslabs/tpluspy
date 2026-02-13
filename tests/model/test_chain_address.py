import pytest

from tplus.model.asset_identifier import ChainAddress


class TestChainAddress:
    @pytest.fixture(scope="class")
    def chain_address(self):
        return ChainAddress.from_str("62622E77D1349Face943C6e7D5c01C61465FE1dc@000000000000aa36a7")

    def test_from_evm_address(self):
        evm_address = "62622E77D1349Face943C6e7D5c01C61465FE1dc"
        chain_address = ChainAddress.from_evm_address(evm_address, 123)
        assert chain_address.evm_address == f"0x{evm_address}"
        assert chain_address.chain_id.vm_id == 123

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
