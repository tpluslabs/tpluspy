from collections.abc import Callable
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
MAIN_SUB_ACCOUNT = 0

UnlockFn = Callable[[], "bytes | Ed25519PrivateKey"]


def _coerce_vk(value: "str | bytes | Ed25519PublicKey") -> Ed25519PublicKey:
    if isinstance(value, Ed25519PublicKey):
        return value
    if isinstance(value, str):
        value = bytes.fromhex(value.removeprefix("0x"))

    return Ed25519PublicKey.from_public_bytes(value)


def _coerce_sk(value: "str | bytes | Ed25519PrivateKey") -> Ed25519PrivateKey:
    if isinstance(value, Ed25519PrivateKey):
        return value
    if isinstance(value, str | bytes):
        key_bytes = privkey_to_bytes(value)
        if len(key_bytes) == 2 * SEED_SIZE:
            key_bytes = key_bytes[:SEED_SIZE]
        elif len(key_bytes) != SEED_SIZE:
            raise ValueError(
                "Ed25519 private keys must be 32 bytes (seed) or 64 bytes (seed+pubkey)"
            )

        return Ed25519PrivateKey.from_private_bytes(key_bytes)
    raise TypeError(f"Unsupported private key type: {type(value)!r}")


class User:
    def __init__(
        self,
        private_key: "str | bytes | Ed25519PrivateKey | None" = None,
        sub_account: int | None = None,
    ):
        if private_key is not None:
            self.sk = _coerce_sk(private_key)
        else:
            self.sk = Ed25519PrivateKey.generate()

        self.vk = self.sk.public_key()
        self._sub_account = sub_account

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.public_key}>"

    @cached_property
    def public_key(self) -> UserPublicKey:
        return UserPublicKey(self.pubkey())

    @cached_property
    def public_key_vec(self) -> list[int]:
        return str_to_vec(self.public_key)

    @property
    def sub_account(self) -> int:
        return self._sub_account or MAIN_SUB_ACCOUNT

    def pubkey(self) -> str:
        return self.vk.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()

    def pubkey_vec(self) -> list[int]:
        return str_to_vec(self.public_key)

    def sign(self, payload: str):
        payload = payload.replace(" ", "")
        payload = payload.replace("\r", "")
        payload = payload.replace("\n", "")
        payload_bytes = payload.encode("utf-8")
        return self.sk.sign(payload_bytes)


class LocalUser(User):
    """A User backed by a local encrypted keyfile that unlocks lazily on first sign."""

    def __init__(
        self,
        public_key: "str | bytes | Ed25519PublicKey",
        unlock: UnlockFn,
        sub_account: int | None = None,
    ):
        self._sk: Ed25519PrivateKey | None = None
        self._unlock = unlock
        self._sub_account = sub_account
        self.vk = _coerce_vk(public_key)

    @property
    def sk(self) -> Ed25519PrivateKey:  # type: ignore[override]
        if self._sk is None:
            sk = _coerce_sk(self._unlock())
            derived = sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            stored = self.vk.public_bytes(Encoding.Raw, PublicFormat.Raw)
            if derived != stored:
                raise ValueError("Unlocked private key does not match stored public key.")

            self._sk = sk

        return self._sk
