import pytest
from ape import convert
from ape.types.address import AddressType
from eth_utils import keccak, to_hex

from tplus.evm.constants import REGISTRY_ADDRESS
from tplus.evm.contracts import DepositVault, Registry, TPlusContract, _decode_erc20_error
from tplus.evm.exceptions import ContractNotExists
from tplus.model.asset_identifier import ChainAddress
from tplus.utils.domain import get_dstack_domain


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
        credential_manager = accounts[2]
        instance = DepositVault.deploy(owner, credential_manager, sender=owner)
        # It should know its address.
        assert instance.address
        assert instance.owner() == owner.address

    def test_deploy_different_owner(self, accounts):
        owner = accounts[0]
        sender = accounts[1]
        deployer_nonce_before = sender.nonce
        credential_manager = accounts[2]
        instance = DepositVault.deploy(owner, credential_manager, sender=sender)
        deployer_nonce_after = sender.nonce
        # It should know its address.
        assert instance.address
        assert instance.owner() == owner.address
        assert deployer_nonce_after > deployer_nonce_before

    def test_from_chain_address(self):
        address = ChainAddress.from_str(
            "62622E77D1349Face943C6e7D5c01C61465FE1dc@000000000000aa36a7"
        )
        vault = DepositVault.from_chain_address(address)
        assert vault.address == address.evm_address

    def test_domain_separator(self, accounts, chain):
        owner = accounts[0]
        credential_manager = accounts[2]

        # Sets domain separator automatically.
        instance = DepositVault.deploy(owner, credential_manager, sender=owner)
        expected = get_dstack_domain(instance.chain_address)
        instance.set_domain_separator(expected, sender=owner)

        # Reads using `eth_getStorageAt()` RPC.
        actual = instance.domain_separator

        assert actual == expected

    def test_chain_address(self, accounts):
        owner = accounts[0]
        instance = DepositVault.deploy(owner, owner, sender=owner)
        actual = instance.chain_address
        assert actual.evm_address == instance.address
        assert actual.chain_id.routing_id == 0
        assert actual.chain_id.vm_id == accounts.chain_manager.chain_id


@pytest.mark.parametrize("error", ("TransferFromFailed()", "TransferFailed()"))
def test_decode_erc20_error(error):
    erc20_error = to_hex(keccak(text=error)[:4])
    actual = _decode_erc20_error(erc20_error)
    assert actual == error
