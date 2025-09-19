from pydantic_core.core_schema import int_schema, no_info_before_validator_function, str_schema

from tplus.utils.serializers import hex_serialize_no_prefix


class UserPublicKey(str):
    """
    A value that validates str, bytes, or list[int] and serializes
    to hex-str without the 0x prefix.
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, value, handler=None):
        schema = no_info_before_validator_function(cls.__validate_user__, str_schema())
        schema["serialization"] = hex_serialize_no_prefix()
        return schema

    @classmethod
    def __validate_user__(cls, value):
        if isinstance(value, str | int | bytes | list):
            return validate_hex_str(value, size=32, pad_right=True)

        from tplus.utils.user import User

        if isinstance(value, User):
            return value.public_key

        # Let pydantic try to handle it.
        return value


def validate_hex_str(value, size: int | None = None, pad_right: bool = False) -> str:
    if isinstance(value, str):
        if value.startswith("0x"):
            value = value[2:]

        value_bytes = bytes.fromhex(value)

    elif isinstance(value, int):
        value_bytes = value.to_bytes(size, "big")

    elif isinstance(value, bytes):
        value_bytes = value

    elif isinstance(value, list):
        value_bytes = bytes(value)

    else:
        raise TypeError(type(value))

    if size is None:
        return value_bytes.hex()

    # Resize.
    adjusted = value_bytes.rjust(size, b"\x00") if pad_right else value_bytes.ljust(size, b"\x00")
    return adjusted.hex()


def validate_hex_int(value, **kwargs):
    if isinstance(value, int):
        return value

    elif isinstance(value, str):
        if value.isnumeric():
            return int(value)

        # Hex-str or fail.
        return int(value, 16)

    elif isinstance(value, bytes):
        return int.from_bytes(value, byteorder="big")

    elif isinstance(value, list):
        return int.from_bytes(bytes(value), byteorder="big")

    raise TypeError(type(value))


class ChainID(int):
    """
    Validated integers, hex-str, and hex-bytes values.
    Serialized to rust-like integer vec.
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, value, handler=None):
        return no_info_before_validator_function(validate_hex_int, int_schema())
