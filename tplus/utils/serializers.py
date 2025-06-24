from typing import Optional

from pydantic_core.core_schema import plain_serializer_function_ser_schema

from tplus.utils.hex import to_vec


def int_vec_serializer(size: Optional[int] = None):
    return plain_serializer_function_ser_schema(
        function=lambda value: to_vec(value, size=size),
    )
