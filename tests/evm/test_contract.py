import pytest

from tplus.evm.constants import REGISTRY_ADDRESS
from tplus.evm.contracts import DepositVault, TPlusContract
from tplus.evm.exceptions import ContractNotExists
from tplus.model.asset_identifier import ChainAddress


class TestTplusContract:
    def test_address_not_exists(self):
        contract = TPlusContract("foo")
        with pytest.raises(ContractNotExists, match=r"foo not deployed on chain '\d*'\."):
            _ = contract.address

    def test_address_from_init(self):
        address = "0x62622E77D1349Face943C6e7D5c01C61465FE1dc"
        contract = TPlusContract("foo", address=address)
        assert contract.address == address

    def test_address_from_lookup(self):
        chain_id = 42161
        contract = TPlusContract("Registry", chain_id=chain_id)
        expected = REGISTRY_ADDRESS
        assert contract.address == expected


class TestDepositVault:
    def test_from_chain_address(self):
        address = ChainAddress(root="62622E77D1349Face943C6e7D5c01C61465FE1dc@a4b1")
        vault = DepositVault.from_chain_address(address)
        assert vault.address == address.evm_address
