import pytest
from eth_utils import keccak

from tplus.evm.exceptions import ContractLogicError
from tplus.evm.governance import (
    OPERATION_EXECUTED_STATUS,
    OPERATION_PENDING_STATUS,
    OperationScheduled,
    OperatorKey,
    apply_operation,
    build_attestation_packet,
    compute_operator_address,
    convert_to_abi_value,
    encode_low_s_signature,
    is_public_key_hex,
    parse_operator_public_key,
    recover_public_key,
    sign_bundle,
)
from tplus.model.representation_rate import RegistryRepresentationConfig
from tplus.utils.operator import SECP256K1_HALF_ORDER, SECP256K1_ORDER

OFF_CURVE_PUBLIC_KEY_RAW = f"{1:064x}{1:064x}"


@pytest.fixture(scope="session")
def digest():
    return keccak(text="tplus governance digest")


@pytest.fixture(scope="session")
def operator_keys():
    return [OperatorKey.create() for _ in range(3)]


def test_operator_key_signature_recovers_its_operator(operator_keys, digest):
    for operator_key in operator_keys:
        signature = operator_key.sign_digest(digest)

        assert int.from_bytes(signature[32:64], "big") <= SECP256K1_HALF_ORDER
        assert recover_public_key(digest, signature) == operator_key.public_key
        assert compute_operator_address(operator_key.public_key) == operator_key.address


def test_encode_low_s_signature_flips_a_high_s_signature(operator_keys, digest):
    low_s_signature = operator_keys[0].sign_digest(digest)
    high_s = SECP256K1_ORDER - int.from_bytes(low_s_signature[32:64], "big")
    high_s_recovery_id = (low_s_signature[64] - 27) ^ 1

    normalized = encode_low_s_signature(
        high_s_recovery_id, low_s_signature[:32], high_s.to_bytes(32, "big")
    )

    assert normalized == low_s_signature


def test_sign_bundle_orders_signers_by_address(operator_keys, digest):
    signers, signatures = sign_bundle(list(reversed(operator_keys)), digest)

    assert signers == sorted(signers, key=lambda address: int(address, 16))
    assert [
        compute_operator_address(recover_public_key(digest, signature)) for signature in signatures
    ] == signers


@pytest.mark.parametrize(
    "build_value, expected",
    [
        pytest.param(lambda key: key.public_key.hex(), True, id="bare"),
        pytest.param(lambda key: f"0x{key.public_key.hex()}", True, id="0x-prefixed"),
        pytest.param(lambda key: f"0x04{key.public_key.hex()}", True, id="uncompressed-prefix"),
        pytest.param(lambda key: key.public_key.hex().upper(), True, id="uppercase"),
        pytest.param(lambda key: key.public_key.hex()[:-1], False, id="one-digit-short"),
        pytest.param(lambda key: f"{key.public_key.hex()[:-1]}g", False, id="non-hex-digit"),
        pytest.param(lambda key: key.address, False, id="address"),
        pytest.param(lambda key: "", False, id="empty"),
    ],
)
def test_is_public_key_hex(operator_keys, build_value, expected):
    assert is_public_key_hex(build_value(operator_keys[0])) is expected


@pytest.mark.parametrize(
    "build_value",
    [
        pytest.param(lambda key: f"{key.address}:{key.public_key.hex()}", id="address-and-key"),
        pytest.param(lambda key: f"0x04{key.public_key.hex()}", id="prefixed-key"),
        pytest.param(lambda key: key.public_key.hex(), id="bare-key"),
    ],
)
def test_parse_operator_public_key_accepts_explicit_keys(operator_keys, build_value):
    operator_key = operator_keys[0]
    assert parse_operator_public_key(build_value(operator_key)) == operator_key.public_key


@pytest.mark.parametrize(
    "build_value, message",
    [
        pytest.param(lambda keys: keys[0].address, "cannot be recovered", id="address-only"),
        pytest.param(
            lambda keys: f"{keys[1].address}:{keys[0].public_key.hex()}",
            "does not derive",
            id="mismatched-address",
        ),
        pytest.param(lambda keys: f"{keys[0].address}:abcd", "64 bytes", id="short-key"),
        pytest.param(lambda keys: OFF_CURVE_PUBLIC_KEY_RAW, "not a point", id="off-curve-key"),
    ],
)
def test_parse_operator_public_key_rejects_unusable_values(operator_keys, build_value, message):
    with pytest.raises(ValueError, match=message):
        parse_operator_public_key(build_value(operator_keys))


@pytest.fixture
def ape_test_account():
    ape = pytest.importorskip("ape")
    return ape.accounts.test_accounts[0]


@pytest.fixture
def resolved_ape_account(mocker, ape_test_account):
    mocker.patch("tplus.evm.governance.resolve_ape_account", return_value=ape_test_account)
    return ape_test_account


def test_parse_operator_public_key_reads_an_ape_alias(resolved_ape_account):
    expected = OperatorKey.from_ape_account(resolved_ape_account).public_key
    assert parse_operator_public_key("example") == expected


@pytest.fixture
def ape_operator_key(ape_test_account):
    return OperatorKey.from_ape_account(ape_test_account)


def test_operator_key_signs_through_an_ape_account(ape_operator_key, digest):
    signature = ape_operator_key.sign_digest(digest)

    assert compute_operator_address(recover_public_key(digest, signature)) == (
        ape_operator_key.address
    )
    assert compute_operator_address(ape_operator_key.public_key) == ape_operator_key.address


@pytest.fixture(scope="session")
def scheduled_operation_id():
    return keccak(text="scheduled operation")


@pytest.fixture
def event_backend(mocker, evm_backend, scheduled_operation_id):
    schedule_event = OperationScheduled(
        op_id=scheduled_operation_id,
        op_type=keccak(text="op type"),
        key=keccak(text="key"),
        lower_eta_secs=0,
        upper_eta_secs=0,
        parameters=b"",
        signers=[],
    )
    mocker.patch.object(
        evm_backend, "get_event_args", return_value=schedule_event.model_dump(by_alias=True)
    )
    return evm_backend


@pytest.fixture
def mock_manager_factory(mocker):
    def build_manager(statuses, execute_error=None):
        manager = mocker.Mock()
        manager.address = "0x00000000000000000000000000000000000000c1"
        manager.deploymentOpType.return_value = keccak(text="deployment op type")
        manager.governanceNonces.return_value = mocker.Mock(lastScheduleNonce=0)
        manager.domainSeparator.return_value = keccak(text="domain separator")
        manager.scheduleOperation.return_value = mocker.sentinel.schedule_receipt
        manager.operation.side_effect = [mocker.Mock(status=status) for status in statuses]
        manager.executeOperation.side_effect = execute_error
        return manager

    return build_manager


@pytest.mark.parametrize(
    "statuses, execute_error",
    [
        pytest.param([OPERATION_EXECUTED_STATUS], None, id="before-status-read"),
        pytest.param(
            [OPERATION_PENDING_STATUS, OPERATION_EXECUTED_STATUS],
            ContractLogicError("NotPending"),
            id="after-status-read",
        ),
    ],
)
def test_apply_operation_treats_another_callers_execute_as_done(
    mock_manager_factory,
    operator_keys,
    event_backend,
    scheduled_operation_id,
    statuses,
    execute_error,
):
    manager = mock_manager_factory(statuses, execute_error)

    op_id = apply_operation(
        manager,
        "SET_WITHDRAWAL_QUORUM",
        [2],
        operator_signers=operator_keys,
        sender=None,
        backend=event_backend,
    )

    assert op_id == scheduled_operation_id
    assert manager.executeOperation.call_count == (0 if execute_error is None else 1)


def test_apply_operation_reraises_an_execute_that_did_not_happen(
    mock_manager_factory, operator_keys, event_backend
):
    manager = mock_manager_factory(
        [OPERATION_PENDING_STATUS, OPERATION_PENDING_STATUS], ContractLogicError("NotReady")
    )

    with pytest.raises(ContractLogicError, match="NotReady"):
        apply_operation(
            manager,
            "SET_WITHDRAWAL_QUORUM",
            [2],
            operator_signers=operator_keys,
            sender=None,
            backend=event_backend,
        )


def test_build_attestation_packet_matches_the_shared_vector(
    domain_separator,
    attestation_quote,
    attestation_sequence,
    operator_key,
    expected_packet_digest,
    expected_packet_signature,
):
    digest, signature = build_attestation_packet(
        domain_separator, attestation_quote, attestation_sequence, operator_key
    )
    assert digest == expected_packet_digest
    assert signature == expected_packet_signature


def test_registry_representation_config_removed_dumps_the_all_zero_struct():
    assert convert_to_abi_value(RegistryRepresentationConfig.removed()) == {
        "providerContract": b"\x00" * 32,
        "staleAfterSecs": 0,
        "maxRateJumpBps": 0,
        "sourceKind": 0,
    }
