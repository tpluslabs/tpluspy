from functools import cached_property

from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # type: ignore
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # type: ignore

from tplus.model.types import UserPublicKey
from tplus.utils.hex import str_to_vec
from tplus.utils.user.validate import privkey_to_bytes

SEED_SIZE = 32


class User:
    def __init__(self, private_key: str | bytes | Ed25519PrivateKey | None = None):
        self._provided_vk_bytes: bytes | None = None
        if private_key:
            if isinstance(private_key, str | bytes):
                private_key_bytes = privkey_to_bytes(private_key)
                if len(private_key_bytes) == 2 * SEED_SIZE:
                    # If a 64-byte key (seed + public key) is provided, keep both parts.
                    self._provided_vk_bytes = private_key_bytes[SEED_SIZE:]
                    private_key_bytes = private_key_bytes[:SEED_SIZE]
                elif len(private_key_bytes) != SEED_SIZE:
                    raise ValueError(
                        "Ed25519 private keys must be 32 bytes (seed) or 64 bytes (seed+pubkey)"
                    )
                self.sk = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
            elif isinstance(private_key, Ed25519PrivateKey):
                self.sk = private_key
            else:
                raise TypeError(f"Unsupported private key type: {type(private_key)!r}")
        else:
            self.sk = Ed25519PrivateKey.generate()

    def __repr__(self) -> str:
        return f"<User {self.public_key}>"

    @cached_property
    def vk(self) -> Ed25519PublicKey:
        # Prefer the provided public key (when available) and validate it once.
        if self._provided_vk_bytes is not None:
            derived_vk_bytes = self.sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            if derived_vk_bytes != self._provided_vk_bytes:
                raise ValueError("Provided Ed25519 public key does not match derived key from seed")
            return Ed25519PublicKey.from_public_bytes(self._provided_vk_bytes)
        return self.sk.public_key

    @cached_property
    def public_key(self) -> UserPublicKey:
        # NOTE: Should effectively be the same as a `str` since base-type.
        return UserPublicKey(self.vk.public_bytes(Encoding.Raw, PublicFormat.Raw).hex())

    @cached_property
    def public_key_vec(self) -> list[int]:
        return str_to_vec(self.public_key)

    # Legacy: use `.public_key` (cached).
    def pubkey(self) -> str:
        return self.public_key

    # Legacy: use `.public_key_vec` (cached).
    def pubkey_vec(self) -> list[int]:
        return str_to_vec(self.public_key)

    def sign(self, payload: str):
        payload = payload.replace(" ", "")
        payload = payload.replace("\r", "")
        payload = payload.replace("\n", "")
        payload_bytes = payload.encode("utf-8")
        signature = self.sk.sign(payload_bytes)
        return signature
