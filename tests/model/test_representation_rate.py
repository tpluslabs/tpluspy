import pytest
from pydantic import ValidationError

from tplus.model.representation_rate import RepresentationRateMappingSnapshot


def test_representation_rate_mapping_snapshot_rejects_a_field_the_api_does_not_have():
    with pytest.raises(ValidationError):
        RepresentationRateMappingSnapshot.model_validate({"overrides": {}})
