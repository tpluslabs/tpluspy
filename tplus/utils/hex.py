def to_vec(val: str | bytes | int, size: int | None = None, pad_right: bool = False) -> list[int]:
    if size is not None and size % 2 != 0:
        raise ValueError("Size must be even.")

    elif isinstance(val, str):
        return str_to_vec(val, size=size)

    elif isinstance(val, int):
        return int_to_vec(val, size=size)

    return _validate_vec_size(list(val), size=size, pad_right=pad_right)


def str_to_vec(hex_str: str, size: int | None = None, pad_right: bool = False) -> list[int]:
    if hex_str.startswith("0x"):
        hex_str = hex_str[2:]

    result = [int(hex_str[i : i + 2], 16) for i in range(0, len(hex_str), 2)]
    return _validate_vec_size(list(result), size=size, pad_right=pad_right)


def int_to_vec(val: int, size: int | None = None, pad_right: bool = False) -> list[int]:
    result = val.to_bytes((val.bit_length() + 7) // 8, byteorder="big")
    return _validate_vec_size(list(result), size=size, pad_right=pad_right)


def _validate_vec_size(val: list[int], size: int | None, pad_right: bool = False) -> list[int]:
    result = list(val)
    length = len(result)

    if size is None:
        # Just make sure is even.
        if length % 2 != 0:
            size = length + 1
            # Process with padding below.

        else:
            # Is an even number; good to go.
            return result

    elif length == size:
        return result

    # If we get here, we are either padding to be even or padding to the give bigger size.
    if length > size:
        raise OverflowError(f"{length} exceeds {size}")

    return _pad_vec(result, size - length, pad_right=pad_right)


def _pad_vec(vec: list[int], pad_amount: int, pad_right: bool = False) -> list[int]:
    padding = [0] * pad_amount
    return vec + padding if pad_right else padding + vec


def to_hex(val, prefix: bool = False) -> str:
    if isinstance(val, str):
        return _str_to_hex(val, prefix=prefix)

    elif isinstance(val, int):
        return _str_to_hex(hex(val), prefix=prefix)

    elif isinstance(val, bytes):
        return _str_to_hex(val.hex(), prefix=prefix)

    raise TypeError(f"{type(val)} cannot be converted to hex.")


def _str_to_hex(val: str, prefix: bool = False) -> str:
    return (
        val
        if val.startswith("0x")
        else f"0x{val}"
        if prefix
        else val[2:]
        if val.startswith("0x")
        else val
    )
