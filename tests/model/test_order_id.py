import pytest
from pydantic import TypeAdapter, ValidationError

from tplus.model.order_id import OID_MAX_LEN_BYTES, UserOrderId


@pytest.mark.parametrize("order_id", ["a" * OID_MAX_LEN_BYTES, "é" * 12])
def test_user_order_id_accepts_up_to_24_utf8_bytes(order_id):
    assert TypeAdapter(UserOrderId).validate_python(order_id) == order_id


@pytest.mark.parametrize("order_id", ["a" * (OID_MAX_LEN_BYTES + 1), "é" * 13])
def test_user_order_id_rejects_more_than_24_utf8_bytes(order_id):
    with pytest.raises(ValidationError, match="Order ID exceeds maximum length of 24 bytes"):
        TypeAdapter(UserOrderId).validate_python(order_id)
