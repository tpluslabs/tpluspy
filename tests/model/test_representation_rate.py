from tplus.model.representation_rate import (
    PreviewUnavailable,
    RepresentationPreviewResponse,
    RepresentationRateHealth,
)


def test_representation_preview_response_parses_awaiting_registry():
    preview = RepresentationPreviewResponse.model_validate(
        {
            "asset": f"{'11' * 32}@000000000000007a69",
            "state_id": "0x00",
            "health": "AwaitingRegistry",
            "approval_available": False,
            "unavailable_reason": "AWAITING_REGISTRY",
            "canonical_amount": 1,
        }
    )

    assert preview.health is RepresentationRateHealth.AWAITING_REGISTRY
    assert preview.unavailable_reason is PreviewUnavailable.AWAITING_REGISTRY
    assert RepresentationRateHealth("InvalidConfig") is RepresentationRateHealth.INVALID_CONFIG
