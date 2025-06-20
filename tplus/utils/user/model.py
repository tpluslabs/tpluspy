from ecdsa import Ed25519, SigningKey

from tplus.utils.hex import str_to_vec
from tplus.utils.user.validate import privkey_to_bytes


class User:
    def __init__(self, private_key: str | bytes | None = None):
        if private_key:
            private_key_bytes = privkey_to_bytes(private_key)
            self.sk = SigningKey.from_string(private_key_bytes, curve=Ed25519)

        else:
            self.sk = SigningKey.generate(curve=Ed25519)

        self.vk = self.sk.verifying_key

    def __repr__(self) -> str:
        return f"<User {self.pubkey()}>"

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
