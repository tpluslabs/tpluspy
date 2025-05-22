from ecdsa import SECP256k1, SigningKey
from Crypto.Hash import keccak


class User:
    def __init__(self, private_key_hex: str | None = None):
        if private_key_hex:
            if private_key_hex.startswith("0x"):
                private_key_hex = private_key_hex[2:]
            private_key_bytes = bytes.fromhex(private_key_hex)
            self.sk = SigningKey.from_string(private_key_bytes, curve=SECP256k1)
        else:
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
    
    @property
    def address(self):
        public_key = self.vk.to_string()
        keccak_hash = keccak.new(digest_bits=256, data=public_key).digest()
        eth_address = "0x" + keccak_hash[-20:].hex()
        return eth_address


if __name__ == "__main__":
    user = User()
    print("Uncompressed public key:", user.pubkey())
    print("Uncompressed public key:", user)
