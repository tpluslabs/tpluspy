def privkey_to_bytes(private_key: str | bytes):
    if isinstance(private_key, bytes):
        return private_key

    # Hex str.
    if private_key.startswith("0x"):
        private_key = private_key[2:]

    return bytes.fromhex(private_key)
