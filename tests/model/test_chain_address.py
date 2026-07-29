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

    def test_model_validate_vault_entry_dict(self):
        entry = {
            "chainId": 42161,
            "routingId": 0,
            "address": "0x62622e77d1349FAce943c6E7D5C01C61465fe1Dc",
        }
        chain_address = ChainAddress.model_validate(entry)
        assert (
            str(chain_address)
            == "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@00000000000000a4b1"
        )
        assert chain_address.chain_id.vm_id == 42161
        assert chain_address.chain_id.routing_id == 0

    def test_model_validate_vault_entry_dict_non_evm(self):
        entry = {"chainId": 101, "routingId": 1, "address": f"0x{'ab' * 32}"}
        chain_address = ChainAddress.model_validate(entry)
        assert str(chain_address) == f"{'ab' * 32}@010000000000000065"
        assert chain_address.chain_id.vm_id == 101
        assert chain_address.chain_id.routing_id == 1
