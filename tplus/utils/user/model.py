import hashlib
from collections.abc import Callable
from functools import cached_property
from typing import TYPE_CHECKING, Any, Protocol, TypeGuard, runtime_checkable

from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # type: ignore
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # type: ignore

from tplus.model.multisig import AdditionalSigner, SignerKey
from tplus.model.types import UserPublicKey
from tplus.utils.hex import str_to_vec
from tplus.utils.user.validate import privkey_to_bytes

if TYPE_CHECKING:
    from ape.api.accounts import AccountAPI

SEED_SIZE = 32
MAIN_SUB_ACCOUNT = 0

UnlockFn = Callable[[], "bytes | Ed25519PrivateKey"]

# Message an EVM wallet signs (EIP-191) to derive its T+ identity. Must stay byte-identical
# to the T+ frontend (and the onboard skill) so a browser wallet and a local ape/eth account
# resolve to the same T+ account.
MASTER_KEY_MESSAGE = (
    "tplus-core: authorize account\n\n"
    "This signature derives your wallet signer key and will never be broadcast to the blockchain."
)


@runtime_checkable
class EvmAccount(Protocol):
    """Structural type for an EVM signer: an Ape ``AccountAPI`` or an ``eth_account`` account."""

    @property
    def address(self) -> str: ...

    def sign_message(self, message: Any, /) -> Any: ...


def is_evm_account(value: Any) -> TypeGuard[EvmAccount]:
    """Whether ``value`` is an EVM account a T+ user can be derived from."""
    return not isinstance(value, User) and isinstance(value, EvmAccount)


def is_ape_account(value: Any) -> "TypeGuard[AccountAPI]":
    """Whether ``value`` is an Ape ``AccountAPI``. Always ``False`` without the ``[evm]`` extra."""
    try:
        from ape.api.accounts import AccountAPI
    except ImportError:
        return False

    return isinstance(value, AccountAPI)


def sign_personal_message(account: "EvmAccount", message: str) -> bytes:
    """Sign ``message`` with an EVM account under EIP-191 (``personal_sign``).

    Args:
        account (EvmAccount): An Ape ``AccountAPI`` or an ``eth_account`` account.
        message (str): The message to sign.

    Returns:
        bytes: The ``r || s || v`` signature.

    Raises:
        ValueError: If an Ape account declines to sign.
    """
    if is_ape_account(account):
        ape_signature = account.sign_message(message)
        if ape_signature is None:
            raise ValueError("Ape account declined to sign.")

        return bytes(ape_signature.encode_rsv())

    from eth_account.messages import encode_defunct

    signed = account.sign_message(encode_defunct(text=message))
    return bytes(signed.signature)


def sign_master_key_message(account: "EvmAccount") -> bytes:
    return sign_personal_message(account, MASTER_KEY_MESSAGE)


def _seed_from_evm_signature(signature: "bytes | bytearray") -> bytes:
    return hashlib.sha512(bytes(signature)).digest()[:SEED_SIZE]


def compact_payload(payload: str) -> str:
    """Strip the whitespace T+ removes before verifying a signed payload."""
    return payload.replace(" ", "").replace("\r", "").replace("\n", "")


def coerce_account_public_key(value: "str | UserPublicKey") -> UserPublicKey:
    """Validate and normalize a T+ account id to lowercase, unprefixed 64-hex."""
    normalized = str(value).removeprefix("0x").lower()
    if len(normalized) != 64:
        raise ValueError("account_public_key must be a 32-byte Ed25519 public key")
    try:
        bytes.fromhex(normalized)
    except ValueError as exc:
        raise ValueError("account_public_key must be hexadecimal") from exc

    return UserPublicKey(normalized)


def resolve_ape_account(account: "str | EvmAccount") -> "EvmAccount":
    """Load an Ape account by alias, or return an already-loaded one unchanged.

    Args:
        account (str | EvmAccount): An Ape account alias, or an ``AccountAPI``.

    Returns:
        EvmAccount: The loaded Ape account.

    Raises:
        ImportError: If the ``[evm]`` extra is not installed.
    """
    if not isinstance(account, str):
        return account

    try:
        from ape import accounts as ape_accounts
    except ImportError as err:
        raise ImportError('Install the "evm" extra to load Ape accounts.') from err

    return ape_accounts.load(account)


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
    """An in-memory T+ user identified by an Ed25519 keypair.

    Args:
        private_key: The Ed25519 private key. Accepts a hex string, raw
            bytes, or an existing :class:`Ed25519PrivateKey`. Both 32-byte
            seeds and 64-byte ``seed || pubkey`` concatenations are
            accepted. If ``None``, a fresh keypair is generated.
        sub_account: Optional sub-account index. Defaults to the main
            sub-account (``0``).
    """

    _evm_address: str | None = None

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

    @classmethod
    def from_evm_account(
        cls,
        account: "EvmAccount",
        sub_account: int | None = None,
        signature: "bytes | None" = None,
    ) -> "User":
        """Derive a T+ user deterministically from an EVM account's EIP-191 signature.

        Works with an Ape ``AccountAPI`` or an ``eth_account`` account. The same EVM key
        always yields the same T+ user, so this is a stable local identity and the account
        a wallet gets when it creates one through tpluspy.

        It is **not** how the T+ frontend identifies an existing account: there the account
        id comes from a ``POST /multisig/signers`` lookup on the wallet's own secp256k1 key,
        and the master key is unrelated to this signature. Use
        :meth:`tplus.client.base.BaseClient.resolve_evm_user` to reach that account.

        Args:
            account (EvmAccount): The EVM account to derive from.
            sub_account (int | None): Optional sub-account index.
            signature (bytes | None): A signature over :data:`MASTER_KEY_MESSAGE` to derive
                from. Supply one to avoid re-prompting the account.

        Returns:
            User: The derived user.
        """
        if signature is None:
            signature = sign_master_key_message(account)

        user = cls(_seed_from_evm_signature(signature), sub_account)
        user._evm_address = account.address
        return user

    @classmethod
    def from_eth_account(cls, account: "EvmAccount", sub_account: int | None = None) -> "User":
        """Derive a T+ user from an ``eth_account`` account (e.g. ``LocalAccount``).

        Args:
            account (EvmAccount): The ``eth_account`` account to derive from.
            sub_account (int | None): Optional sub-account index.

        Returns:
            User: The derived user.
        """
        return cls.from_evm_account(account, sub_account=sub_account)

    @classmethod
    def from_ape_account(
        cls, account: "str | EvmAccount", sub_account: int | None = None
    ) -> "User":
        """Derive a T+ user from an Ape account. Requires the ``[evm]`` extra.

        Args:
            account (str | EvmAccount): An Ape account alias, or an ``AccountAPI``.
            sub_account (int | None): Optional sub-account index.

        Returns:
            User: The derived user.
        """
        return cls.from_evm_account(resolve_ape_account(account), sub_account=sub_account)

    @property
    def evm_address(self) -> str | None:
        """EVM address this user was derived from, if any."""
        return self._evm_address

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.public_key}>"

    @cached_property
    def public_key(self) -> UserPublicKey:
        """Hex-encoded Ed25519 public key (no ``0x`` prefix)."""
        return UserPublicKey(self.pubkey())

    @cached_property
    def public_key_vec(self) -> list[int]:
        """Public key as a list of byte-valued integers."""
        return str_to_vec(self.public_key)

    @property
    def sub_account(self) -> int:
        """Active sub-account index. Defaults to the main sub-account."""
        return self._sub_account or MAIN_SUB_ACCOUNT

    def pubkey(self) -> str:
        """Return the hex-encoded raw Ed25519 public key."""
        return self.vk.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()

    def pubkey_vec(self) -> list[int]:
        """Return the public key as a list of byte-valued integers."""
        return str_to_vec(self.public_key)

    def sign(self, payload: str):
        """Sign ``payload`` with the user's Ed25519 private key.

        Whitespace (spaces, ``\\r``, ``\\n``) is stripped before signing so
        that callers can pass pretty-printed JSON; T+ canonicalises payloads
        as compact JSON before verifying.

        Args:
            payload: UTF-8 string to sign.

        Returns:
            The 64-byte raw Ed25519 signature.
        """
        payload = payload.replace(" ", "")
        payload = payload.replace("\r", "")
        payload = payload.replace("\n", "")
        payload_bytes = payload.encode("utf-8")
        return self.sk.sign(payload_bytes)

    def signing_parts(self, payload: str) -> tuple[list[int], list[AdditionalSigner]]:
        """Return the master and additional signatures for a request payload."""
        return list(self.sign(payload)), []


class DelegatedUser(User):
    """Act for one account using a registered Ed25519 additional signer.

    ``account_public_key`` identifies the account in request payloads and auth
    headers. ``signer`` supplies the co-signature; its private key is never
    treated as the account's master key.
    """

    def __init__(
        self,
        account_public_key: str | UserPublicKey,
        signer: User,
        sub_account: int | None = None,
    ) -> None:
        if isinstance(signer, DelegatedUser):
            raise ValueError("signer must be a master-key User, not another DelegatedUser")

        # Deliberately do not call User.__init__: generating an unrelated master
        # key would make direct-signing code appear to work for the wrong account.
        self._account_public_key = coerce_account_public_key(account_public_key)
        self._signer = signer
        self._sub_account = sub_account

    @property
    def sk(self) -> Ed25519PrivateKey:  # type: ignore[override]
        # AttributeError (not ValueError) keeps hasattr()/getattr() semantics.
        raise AttributeError("DelegatedUser has no account master private key")

    @property
    def vk(self) -> Ed25519PublicKey:  # type: ignore[override]
        raise AttributeError("DelegatedUser has no account master public-key object")

    @cached_property
    def public_key(self) -> UserPublicKey:
        return self._account_public_key

    @cached_property
    def public_key_vec(self) -> list[int]:
        return str_to_vec(self.public_key)

    def pubkey(self) -> str:
        return self.public_key

    def pubkey_vec(self) -> list[int]:
        return self.public_key_vec

    def sign(self, payload: str):
        """Reject direct signing, which has no co-signer wire-format context."""
        raise ValueError(
            "Delegated users cannot produce master signatures; use signing_parts() "
            "for request types that support additional signers."
        )

    def signing_parts(self, payload: str) -> tuple[list[int], list[AdditionalSigner]]:
        additional = AdditionalSigner(
            signer=SignerKey.ed25519(self._signer.public_key_vec),
            signature=list(self._signer.sign(payload)),
        )
        return [], [additional]


class LocalUser(User):
    """A :class:`User` backed by a local encrypted keyfile.

    The public key is loaded eagerly from the ``.pub`` sidecar; the private
    key is decrypted lazily on the first call to :meth:`sign`. This lets
    callers list and identify users without prompting for a password.

    Args:
        public_key: Hex-encoded Ed25519 public key, raw bytes, or an
            existing :class:`Ed25519PublicKey`.
        unlock: Callable returning the raw private key (or
            :class:`Ed25519PrivateKey`) when invoked. Typically wraps a
            password prompt and a decrypt step.
        sub_account: Optional sub-account index.
    """

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
