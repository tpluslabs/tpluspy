from typing import Annotated

from pydantic import AfterValidator

OID_MAX_LEN_BYTES = 24


def validate_order_id(order_id: str) -> str:
    length = len(order_id.encode("utf-8"))
    if length > OID_MAX_LEN_BYTES:
        raise ValueError(
            f"Order ID exceeds maximum length of {OID_MAX_LEN_BYTES} bytes (got {length})"
        )
    return order_id


UserOrderId = Annotated[str, AfterValidator(validate_order_id)]
