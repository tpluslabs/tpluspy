from tplus.evm.contracts import DepositVault
from tplus.model.asset_identifier import ChainAddress


class TestDepositVault:
    def test_from_chain_address(self):
        address = ChainAddress(root="62622E77D1349Face943C6e7D5c01C61465FE1dc@a4b1")
        vault = DepositVault.from_chain_address(address)
        assert vault.address == address.evm_address
