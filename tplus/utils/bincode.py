import struct


def encode_u64(value: int) -> bytes:
    return struct.pack("<Q", value)


def encode_bytes(value: bytes) -> bytes:
    return encode_u64(len(value)) + value
