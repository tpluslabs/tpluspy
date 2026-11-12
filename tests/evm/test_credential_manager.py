import pytest
from eth_utils import to_checksum_address

from tests.evm.conftest import build_eth_tester_web3
from tplus.evm.backends.web3 import Web3Backend
from tplus.evm.contracts import (
    DEV_TCB_EVALUATION_NUMBER,
    DEV_UNIVERSE_ID,
    DepositVault,
    read_genesis,
)
from tplus.evm.governance import OperationScheduled, OperatorKey, build_mock_quote
from tplus.model.config import ChainConfig


@pytest.fixture
def vault_factory():
    def deploy_registered_vault(owner, manager, operator_keys):
        # A vault's genesis is the manager's committed snapshot, which exists once attested
        # keys reach the withdrawal quorum. Each operator starts with its own address as key.
        for operator_key in operator_keys:
            manager.attest_signer(operator_key, operator_key.address, sender=owner)

        vault = DepositVault.deploy_proxy(owner, manager.address, sender=owner)
        manager.add_vault(
            vault.chain_address, ChainConfig.dev(), operator_keys=operator_keys, sender=owner
        )
        return vault

    return deploy_registered_vault


@pytest.fixture
def manager_stack_factory(manager_factory, vault_factory):
    def build_manager_stack(operator_keys, universe_id=DEV_UNIVERSE_ID):
        owner, _, manager = manager_factory(operator_keys, len(operator_keys), universe_id)
        vault = vault_factory(owner, manager, operator_keys)
        manager.register_intra_chain_strategy(
            vault.chain_address.chain_id, operator_keys=operator_keys, sender=owner
        )
        return owner, manager, vault

    return build_manager_stack


@pytest.fixture
def operator_keys():
    return [OperatorKey.create() for _ in range(2)]


@pytest.fixture
def signer_keys():
    return [OperatorKey.create().address for _ in range(2)]


def test_credential_manager_attests_rotates_and_syncs_a_vault(
    manager_stack_factory, operator_keys, signer_keys
):
    owner, manager, vault = manager_stack_factory(operator_keys)
    assert int(manager.automataVerifier(), 16) == 0

    for operator_key, signer_key in zip(operator_keys, signer_keys, strict=True):
        op_id = manager.attest(
            build_mock_quote(signer_key, operator_key.address), operator_key, sender=owner
        )
        manager.execute_key_rotation(op_id, operator_key.address, signer_key, sender=owner)

        assert manager.get_attested_key(operator_key.address) == signer_key

    manager.set_withdrawal_quorum(2, operator_keys=operator_keys, sender=owner)
    manager.sync_vault_governance_snapshot(vault.chain_address.chain_id, sender=owner)

    assert manager.withdrawalQuorum() == 2
    assert vault.withdrawalQuorum() == 2
    assert all(vault.isAdministrator(signer_key) for signer_key in signer_keys)


def test_install_vault_signers_attests_once_and_always_syncs(
    manager_stack_factory, operator_keys, signer_keys
):
    operator_key, signer_key = operator_keys[0], signer_keys[0]
    owner, manager, vault = manager_stack_factory([operator_key])

    manager.install_vault_signers(vault, operator_key, signer_key, sender=owner)
    sequence = manager.lastAttestationSequence(operator_key.address)
    sync_receipt = manager.install_vault_signers(vault, operator_key, signer_key, sender=owner)

    assert vault.isAdministrator(signer_key)
    # The vault's genesis took the operator's first attestation and the manager's first commit.
    assert manager.lastAttestationSequence(operator_key.address) == sequence == 2
    sync_event = manager.backend.get_event_args(
        sync_receipt, manager.contract, "VaultGovernanceSnapshotSyncSubmitted"
    )
    assert sync_event["version"] == 2


def test_submit_node_attestation_accepts_the_shared_vector(
    manager_factory,
    attestation_universe_id,
    operator_key,
    attestation_quote,
    attestation_sequence,
    expected_packet_digest,
    expected_packet_signature,
):
    owner, _, manager = manager_factory([operator_key], 1, attestation_universe_id)
    signer_key = to_checksum_address(attestation_quote[:20])

    receipt = manager.submitNodeAttestationOnChain(
        attestation_quote,
        DEV_TCB_EVALUATION_NUMBER,
        attestation_sequence,
        expected_packet_signature,
        sender=owner,
    )
    schedule_event = OperationScheduled.from_receipt(receipt, manager.contract, manager.backend)
    op_id = bytes(schedule_event.op_id)
    manager.execute_key_rotation(op_id, operator_key.address, signer_key, sender=owner)

    assert bytes(manager.attestationPacketDigest(attestation_quote, attestation_sequence)) == (
        expected_packet_digest
    )
    assert manager.get_attested_key(operator_key.address) == signer_key


def test_vault_behind_a_receiver_starts_from_a_manager_on_another_chain(
    manager_factory, operator_keys, signer_keys
):
    owner, _, manager = manager_factory(operator_keys, len(operator_keys))
    for operator_key, signer_key in zip(operator_keys, signer_keys, strict=True):
        manager.attest_signer(operator_key, signer_key, sender=owner)

    # A second chain, where the vault's credential manager is a receiver with no snapshot.
    vault_chain = Web3Backend(web3=build_eth_tester_web3(), is_local=True)
    vault_owner = vault_chain.default_test_account()
    receiver = to_checksum_address("0x" + "ee" * 20)
    genesis = read_genesis(manager.address, backend=manager.backend)

    vault = DepositVault.deploy_proxy(
        vault_owner, receiver, sender=vault_owner, genesis=genesis, backend=vault_chain
    )

    assert genesis == manager.get_governance_snapshot()
    assert to_checksum_address(vault.credentialManager()) == receiver
    assert vault.withdrawalQuorum() == manager.withdrawalQuorum()
    assert all(vault.isAdministrator(signer_key) for signer_key in signer_keys)
    assert not any(vault.isAdministrator(operator_key.address) for operator_key in operator_keys)
