from pydantic_core.core_schema import (
    no_info_before_validator_function,
    no_info_plain_validator_function,
    str_schema,
)

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

    elif isinstance(value, int) and size is not None:
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


class ChainID(str):
    def __new__(cls, value: str):
        # Always store as lowercase hex string
        return super().__new__(cls, value.lower())

    @property
    def routing_id(self) -> int:
        return int(self[:2], 16)

    @property
    def vm_id(self) -> int:
        return int(self[2:], 16)

    @classmethod
    def evm(cls, vm_id: int) -> "ChainID":
        return cls.from_parts(0, vm_id)

    @classmethod
    def from_parts(cls, routing_id: int, vm_id: int) -> "ChainID":
        if not (0 <= routing_id < 256):
            raise ValueError("routing_id must be 0-255")

        elif not (0 <= vm_id < 2**64):
            raise ValueError("vm_id must fit in 8 bytes")

        return cls(f"{routing_id:02x}{vm_id:016x}")

    def to_bytes(self) -> bytes:
        return bytes.fromhex(self)

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        """
        This tells Pydantic how to validate / coerce ChainID.
        Accepts str, bytes, or dict.
        """
        return no_info_plain_validator_function(cls._validator)

    @classmethod
    def _validator(cls, value: str | bytes | dict) -> "ChainID":
        if isinstance(value, str):
            value = value.removeprefix("0x")
            if len(value) != 18:
                raise ValueError("Hex string must be exactly 18 chars (9 bytes)")

            return cls(value)

        elif isinstance(value, bytes):
            if len(value) != 9:
                raise ValueError("Bytes must be exactly 9 bytes")

            return cls(value.hex())

        elif isinstance(value, dict):
            if "routing_id" not in value or "vm_id" not in value:
                raise ValueError("Dict must contain routing_id and vm_id")

            return cls.from_parts(int(value["routing_id"]), int(value["vm_id"]))

        elif isinstance(value, list):
            if len(value) != 9:
                raise ValueError(
                    f"List[int] must have exactly 9 elements (received {len(value)} elements)"
                )

            elif not all(isinstance(b, int) and 0 <= b < 256 for b in value):
                raise ValueError("All list elements must be ints 0-255")

            return cls(bytes(value).hex())

        raise TypeError(f"Cannot coerce {type(value)} to ChainID")

    def __eq__(self, other):
        if not isinstance(other, ChainID):
            if other.startswith("0x"):
                other = other[2:]

        return f"{self}" == other
