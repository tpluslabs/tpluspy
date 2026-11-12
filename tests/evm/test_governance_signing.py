import pytest
from eth_utils import keccak

from tplus.evm.contracts import DEV_UNIVERSE_ID, MeasurementProfileRegistry
from tplus.evm.governance import OperatorKey, sign_bundle


def assert_ascending(addresses):
    assert list(addresses) == sorted(addresses, key=lambda address: int(address, 16))


@pytest.mark.parametrize(
    "member_count, threshold",
    [pytest.param(1, 1, id="one-signer"), pytest.param(3, 2, id="k-of-n")],
)
def test_sign_bundle_is_accepted_by_every_governance_host(
    manager_factory, measurement_profile, member_count, threshold
):
    members = [OperatorKey.create() for _ in range(member_count)]
    signers = sorted(members, key=lambda member: int(member.address, 16), reverse=True)[:threshold]
    owner, registry, manager = manager_factory(members, threshold)
    member_addresses = [member.address for member in members]
    registry.initialize_risk_council(
        manager.address, DEV_UNIVERSE_ID, member_addresses, threshold, sender=owner
    )
    profile_registry = MeasurementProfileRegistry.deploy(
        sender=owner, credential_manager=manager.address, universe_id=DEV_UNIVERSE_ID
    )

    manager.set_profile_registry(profile_registry.address, operator_keys=signers, sender=owner)
    council_event = registry.schedule_and_execute_if_due(
        "RISK_COUNCIL", [member_addresses, threshold], council=signers, sender=owner
    )
    profile_event = profile_registry.schedule_profile(
        MeasurementProfileRegistry.CLEARING_ENGINE_KIND,
        measurement_profile,
        operator_keys=signers,
        sender=owner,
    )

    assert manager.measurementProfileRegistry() == profile_registry.address
    assert len(council_event.signers) == len(profile_event.signers) == threshold
    assert_ascending(council_event.signers)
    assert_ascending(profile_event.signers)


def test_sign_bundle_rejects_no_signers():
    with pytest.raises(ValueError, match="at least one signer"):
        sign_bundle([], keccak(text="digest"))
