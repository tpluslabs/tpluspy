"""
Demo deploy script for quickly getting some state in the contracts.
"""

import click
from ape import Contract, chain
from ape.cli import ConnectedProviderCommand, account_option
from eip712.messages import _prepare_data_for_hashing
from eth_account._utils.encode_typed_data import hash_domain

from tplus.contracts import address_to_bytes32, get_test_erc20_type, registry, vault
from tplus.eip712 import Domain


@click.command(cls=ConnectedProviderCommand)
@account_option()
def cli(account, network):
    # Deploy the registry.
    deploy(account, network)


def deploy(account, network):
    registry.deploy(account)
    registry.setCouncilMultisig(account, sender=account)
    registry.setRiskManagerMultisig(account, sender=account)

    # Deploy the vault.
    vault.deploy(account)

    # TODO: simply one https://github.com/ApeWorX/eip712/pull/63 is released.
    domain = Domain()
    domain = _prepare_data_for_hashing(domain._domain_["domain"])
    domain_separator = hash_domain(domain)

    vault.setDomainSeparator(domain_separator, sender=account)

    chain_id = chain.chain_id
    erc20 = get_test_erc20_type()
    if chain_id == 11155111:
        token1 = Contract("0x62622E77D1349Face943C6e7D5c01C61465FE1dc", contract_type=erc20)
        token2 = Contract("0x58372ab62269A52fA636aD7F200d93999595DCAF", contract_type=erc20)
    else:
        # No tokens yet.
        return

    # Set each asset token.
    chain_id = chain.chain_id
    for idx, tkn in enumerate((token1, token2)):
        data = {
            "assetAddress": address_to_bytes32(tkn.address),
            "chainId": chain_id,
            "maxDeposits": 10,
        }
        registry.setAssetData(idx, data, sender=account)
