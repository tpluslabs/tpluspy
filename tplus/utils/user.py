from ecdsa import SECP256k1, SigningKey, VerifyingKey
import logging
from Crypto.Hash import keccak

logger = logging.getLogger(__name__)

class User:
    def __init__(self, private_key_hex: str = None):
        if private_key_hex:
            try:
                self.sk = SigningKey.from_string(bytes.fromhex(private_key_hex), curve=SECP256k1)
            except ValueError as e:
                logger.debug(f"Private key is not valid hex, checking for ethereum private key format")
                try:
                    self.sk = SigningKey.from_string(bytes.fromhex(private_key_hex.lstrip("0x")), curve=SECP256k1)
                except Exception as e:
                    logger.error(f"Error creating user from private key: {type(e).__name__} - {e}")
                    raise
        else:
            logger.warning("No private key provided, generating new key")
            self.sk = SigningKey.generate(curve=SECP256k1)
        self.vk: VerifyingKey = self.sk.verifying_key

    def pubkey(self):
        uncompressed_pubkey = b"\x04" + self.vk.to_string()
        hex_pubkey = uncompressed_pubkey.hex()
        return hex_pubkey

    @property
    @staticmethod
    def address(self):
        """
        Calculates the Ethereum address from the public key.
        """
        pubkey_bytes = self.vk.to_string("uncompressed")[1:]  # Remove the 0x04 prefix
        keccak_hash = keccak.new(digest_bits=256)
        keccak_hash.update(pubkey_bytes)
        address_bytes = keccak_hash.digest()[-20:]
        return "0x" + address_bytes.hex()

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
