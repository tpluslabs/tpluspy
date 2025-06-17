from ecdsa import Ed25519, SigningKey

from tplus.utils.hex import str_to_vec


class User:
    def __init__(self, private_key_hex: str | None = None):
        if private_key_hex:
            if private_key_hex.startswith("0x"):
                private_key_hex = private_key_hex[2:]

            private_key_bytes = bytes.fromhex(private_key_hex)
            self.sk = SigningKey.from_string(private_key_bytes, curve=Ed25519)

        else:
            self.sk = SigningKey.generate(curve=Ed25519)

        self.vk = self.sk.verifying_key

    def pubkey(self) -> str:
        return self.vk.to_string().hex()

    def pubkey_vec(self) -> list[str]:
        return str_to_vec(self.pubkey())

    def sign(self, payload: str):
        payload = payload.replace(" ", "")
        payload = payload.replace("\r", "")
        payload = payload.replace("\n", "")
        payload_bytes = payload.encode("utf-8")
        signature = self.sk.sign(payload_bytes)
        return signature


if __name__ == "__main__":
    user = User()
    print("Uncompressed public key:", user.pubkey(), ", length:", len(user.pubkey()))
