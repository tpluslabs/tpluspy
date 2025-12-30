import pytest
from ape import convert
from ape.types.address import AddressType
from eth_utils import keccak, to_hex

from tplus.evm.constants import REGISTRY_ADDRESS
from tplus.evm.contracts import DepositVault, Registry, TPlusContract, _decode_erc20_error
from tplus.evm.eip712 import Domain
from tplus.evm.exceptions import ContractNotExists
from tplus.model.asset_identifier import ChainAddress


class TestTplusContract:
    def test_convert_to_address(self):
        address = "0x62622E77D1349Face943C6e7D5c01C61465FE1dc"
        contract = TPlusContract("foo", address=address)
        assert convert(contract, AddressType) == address

    def test_address_not_exists(self):
        class FooContract(TPlusContract):
            NAME = "foo"

        contract = FooContract()
        with pytest.raises(ContractNotExists, match=r"foo not deployed on chain '\d*'\."):
            _ = contract.address

    def test_address_from_init(self):
        address = "0x62622E77D1349Face943C6e7D5c01C61465FE1dc"
        contract = TPlusContract("foo", address=address)
        assert contract.address == address

    def test_address_from_lookup(self):
        chain_id = 42161
        contract = Registry(chain_id=chain_id)
        expected = REGISTRY_ADDRESS
        assert contract.address == expected


class TestDepositVault:
    def test_deploy(self, accounts):
        owner = accounts[0]
        instance = DepositVault.deploy(sender=owner)
        # It should know its address.
        assert instance.address
        assert instance.owner() == owner.address

    def test_deploy_different_owner(self, accounts):
        owner = accounts[0]
        sender = accounts[1]
        deployer_nonce_before = sender.nonce
        instance = DepositVault.deploy(owner, sender=sender)
        deployer_nonce_after = sender.nonce
        # It should know its address.
        assert instance.address
        assert instance.owner() == owner.address
        assert deployer_nonce_after > deployer_nonce_before

    def test_from_chain_address(self):
        address = ChainAddress(root="62622E77D1349Face943C6e7D5c01C61465FE1dc@a4b1")
        vault = DepositVault.from_chain_address(address)
        assert vault.address == address.evm_address

    def test_domain_separator(self, accounts, chain):
        owner = accounts[0]

        # Sets domain separator automatically.
        instance = DepositVault.deploy(sender=owner)

        expected = Domain(chain.chain_id, instance.address).separator

        # Reads using `eth_getStorageAt()` RPC.
        actual = instance.domain_separator

        assert actual == expected


@pytest.mark.parametrize("error", ("TransferFromFailed()", "TransferFailed()"))
def test_decode_erc20_error(error):
    erc20_error = to_hex(keccak(text=error)[:4])
    actual = _decode_erc20_error(erc20_error)
    assert actual == error
