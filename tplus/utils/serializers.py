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


def to_u256_str(value: int | str) -> str:
    """Canonical base-10 wire form for a U256 field."""
    return str(int(value))


def parse_int(value: int | str | None) -> int:
    """Read a U256 that may arrive as a base-10 string or as `0x`-prefixed hex.

    Struct fields are canonical base-10; amounts reached through a map value or a type
    alias (spot balances) still carry the `0x` form, so the prefix picks the base.
    """
    if value is None:
        return 0

    if isinstance(value, int):
        return value

    text = str(value).strip().lower()
    if text.startswith("0x"):
        return int(text, 16)

    return int(text)
