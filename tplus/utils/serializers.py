from pydantic_core.core_schema import plain_serializer_function_ser_schema

from tplus.utils.hex import to_hex, to_vec


def int_vec_serializer(size: int | None = None):
    return plain_serializer_function_ser_schema(
        function=lambda value: to_vec(value, size=size),
    )


def hex_serialize_no_prefix(prefix: bool = False):
    return plain_serializer_function_ser_schema(
        function=lambda value: to_hex(value, prefix=prefix),
    )
