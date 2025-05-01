from ecdsa import SECP256k1, SigningKey


class User:
    def __init__(self):
        self.sk = SigningKey.generate(curve=SECP256k1)
        self.vk = self.sk.verifying_key

    def pubkey(self):
        uncompressed_pubkey = b"\x04" + self.vk.to_string()
        hex_pubkey = uncompressed_pubkey.hex()
        return hex_pubkey

    def sign(self, payload: str):
        payload = payload.replace(" ", "")
        payload = payload.replace("\r", "")
        payload = payload.replace("\n", "")
        payload_bytes = payload.encode("utf-8")
        signature = self.sk.sign(payload_bytes)
        return signature


if __name__ == "__main__":
    user = User()
    print("Uncompressed public key:", user.pubkey())
    print("Uncompressed public key:", user)
