def to_vec(hex_val: str | bytes) -> list[int]:
    if isinstance(hex_val, str):
        return str_to_vec(hex_val)

    return list(hex_val)


def str_to_vec(hex_str: str) -> list[int]:
    if hex_str.startswith("0x"):
        hex_str = hex_str[2:]

    return [int(hex_str[i : i + 2], 16) for i in range(0, len(hex_str), 2)]
