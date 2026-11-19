from tplus.evm.contracts import DEV_UNIVERSE_ID, MeasurementProfile, MeasurementProfileRegistry
from tplus.evm.governance import OperatorKey


def test_measurement_profile_registry_sets_profiles_through_the_committee(
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

    second_profile = MeasurementProfile(*(bytes([register]) * 32 for register in range(6, 11)))
    profiles = [measurement_profile, second_profile]
    schedule_event = profile_registry.schedule_profiles(
        MeasurementProfileRegistry.CLEARING_ENGINE_KIND,
        profiles,
        operator_keys=operator_keys,
        sender=owner,
    )
    profile_registry.execute_profiles(
        bytes(schedule_event.op_id),
        MeasurementProfileRegistry.CLEARING_ENGINE_KIND,
        profiles,
        sender=owner,
    )

    assert manager.measurementProfileRegistry() == profile_registry.address
    assert [
        tuple(map(bytes, profile))
        for profile in profile_registry.profiles(MeasurementProfileRegistry.CLEARING_ENGINE_KIND)
    ] == profiles
    assert not profile_registry.profiles(MeasurementProfileRegistry.CLEARING_ENGINE_KIND + 1)
