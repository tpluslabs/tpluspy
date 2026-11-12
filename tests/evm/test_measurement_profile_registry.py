from tplus.evm.contracts import DEV_UNIVERSE_ID, MeasurementProfileRegistry
from tplus.evm.governance import OperatorKey


def test_measurement_profile_registry_sets_a_profile_through_the_committee(
    manager_factory, measurement_profile
):
    operator_keys = [OperatorKey.create()]
    owner, _, manager = manager_factory(operator_keys, 1)
    profile_registry = MeasurementProfileRegistry.deploy(
        sender=owner, credential_manager=manager.address, universe_id=DEV_UNIVERSE_ID
    )
    manager.set_profile_registry(
        profile_registry.address, operator_keys=operator_keys, sender=owner
    )

    schedule_event = profile_registry.schedule_profile(
        MeasurementProfileRegistry.CLEARING_ENGINE_KIND,
        measurement_profile,
        operator_keys=operator_keys,
        sender=owner,
    )
    profile_registry.execute_profile(
        bytes(schedule_event.op_id),
        MeasurementProfileRegistry.CLEARING_ENGINE_KIND,
        measurement_profile,
        sender=owner,
    )

    assert manager.measurementProfileRegistry() == profile_registry.address
    assert (
        tuple(map(bytes, profile_registry.profile(MeasurementProfileRegistry.CLEARING_ENGINE_KIND)))
        == measurement_profile
    )
    assert not any(
        bytes(profile_registry.profile(MeasurementProfileRegistry.CLEARING_ENGINE_KIND + 1)[0])
    )
