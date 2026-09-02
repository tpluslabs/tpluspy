import importlib.util

import pytest
from eth_utils import keccak, to_hex

from tplus.evm.constants import REGISTRY_ADDRESS
from tplus.evm.contracts import (
    DepositVault,
    Registry,
    TPlusContract,
    _decode_erc20_error,
)
from tplus.evm.exceptions import ContractNotExists
from tplus.model.asset_identifier import ChainAddress
from tplus.utils.domain import get_dstack_domain

_HAS_APE = importlib.util.find_spec("ape") is not None
ape_only = pytest.mark.skipif(not _HAS_APE, reason="requires Ape (tpluspy[evm-ape])")


# -- Pure tests (no backend connection needed) --------------------------------


class TestTplusContract:
    def test_address_from_init(self):
        address = "0x62622E77D1349Face943C6e7D5c01C61465FE1dc"
        contract = TPlusContract("foo", address=address)
        assert contract.address == address

    def test_address_from_lookup(self):
        contract = Registry(chain_id=42161)
        assert contract.address == REGISTRY_ADDRESS

    def test_address_not_exists(self, evm_backend):
        class FooContract(TPlusContract):
            NAME = "foo"

        contract = FooContract()
        with pytest.raises(ContractNotExists, match=r"foo not deployed on chain '\d*'\."):
            _ = contract.address


class TestDepositVault:
    def test_from_chain_address(self):
        address = ChainAddress.from_str(
            "62622E77D1349Face943C6e7D5c01C61465FE1dc@000000000000aa36a7"
        )
        vault = DepositVault.from_chain_address(address)
        assert vault.address == address.evm_address


@pytest.mark.parametrize("error", ("TransferFromFailed()", "TransferFailed()"))
def test_decode_erc20_error(error):
    erc20_error = to_hex(keccak(text=error)[:4])
    actual = _decode_erc20_error(erc20_error)
    assert actual == error


# -- Backend-driven tests (run under whichever backend is set up) -------------


class TestDepositVaultDeploy:
    def test_deploy(self, evm_backend, test_accounts):
        owner = test_accounts[0]
        credential_manager = test_accounts[2]
        instance = DepositVault.deploy(owner, credential_manager, sender=owner)
        assert instance.address
        assert instance.owner() == evm_backend.convert_address(owner)

    def test_deploy_different_owner(self, evm_backend, test_accounts):
        owner = test_accounts[0]
        sender = test_accounts[1]
        credential_manager = test_accounts[2]
        nonce_before = sender.nonce
        instance = DepositVault.deploy(owner, credential_manager, sender=sender)
        assert instance.address
        assert instance.owner() == evm_backend.convert_address(owner)
        assert sender.nonce > nonce_before

    def test_domain_separator(self, evm_backend, test_accounts):
        owner = test_accounts[0]
        credential_manager = test_accounts[2]

        instance = DepositVault.deploy(owner, credential_manager, sender=owner)
        expected = get_dstack_domain(instance.chain_address)
        instance.set_domain_separator(expected, sender=owner)

        # Reads using ``eth_getStorageAt`` -- backend-neutral.
        assert instance.domain_separator == expected

    def test_chain_address(self, evm_backend, test_accounts):
        owner = test_accounts[0]
        instance = DepositVault.deploy(owner, owner, sender=owner)
        actual = instance.chain_address
        assert actual.evm_address == instance.address
        assert actual.chain_id.routing_id == 0
        assert actual.chain_id.vm_id == evm_backend.chain_id


# -- Ape-only tests (Ape's ``convert`` API + Ape-backend assertion) -----------


@ape_only
def test_active_backend_is_ape(evm_backend):
    from tplus.evm.backends.ape import ApeBackend

    assert isinstance(evm_backend, ApeBackend)
    assert evm_backend.name == "ape"
    assert evm_backend.is_local_network


@ape_only
def test_convert_to_address():
    from ape import convert
    from ape.types.address import AddressType

    address = "0x62622E77D1349Face943C6e7D5c01C61465FE1dc"
    contract = TPlusContract("foo", address=address)
    assert convert(contract, AddressType) == address
