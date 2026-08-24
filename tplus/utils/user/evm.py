"""Identity for an EVM wallet that is a registered signer on a T+ account.

T+ accounts created from a wallet register the wallet's own secp256k1 key as an additional
signer. The account id is unrelated to that key and is found by looking the signer up, so
reaching such an account is a two-step affair: recover the signer key here, resolve the
account with :meth:`tplus.client.base.BaseClient.resolve_evm_user`.
"""

import hashlib
from functools import cached_property

from tplus.model.multisig import AdditionalSigner, SignerKey
from tplus.model.types import UserPublicKey
from tplus.utils.user.model import (
    MASTER_KEY_MESSAGE,
    SEED_SIZE,
    DelegatedUser,
    EvmAccount,
    coerce_account_public_key,
    compact_payload,
    sign_master_key_message,
    sign_personal_message,
)

EIP191_PREFIX = b"\x19Ethereum Signed Message:\n"


def _eip191_hash(message: str) -> bytes:
    from eth_utils import keccak

    body = message.encode("utf-8")
    return keccak(EIP191_PREFIX + str(len(body)).encode("ascii") + body)


def _require_eth_keys():
    try:
        from eth_keys import KeyAPI
    except ImportError as err:
        raise ImportError(
            'Recovering a wallet signer key needs `eth-keys`; install "tpluspy[evm]" or '
            "`eth-account`."
        ) from err

    return KeyAPI()


def recover_signer_key(signature: "bytes | bytearray") -> bytes:
    """Recover the wallet's compressed secp256k1 public key from its identity signature.

    This is the key T+ registers as an account's wallet signer, and the one a
    ``POST /multisig/signers`` lookup resolves to an account id.

    Args:
        signature (bytes | bytearray): A signature over :data:`MASTER_KEY_MESSAGE`.

    Returns:
        bytes: The 33-byte compressed public key.
    """
    key_api = _require_eth_keys()
    signature = bytes(signature)
    if len(signature) != 65:
        raise ValueError("EIP-191 signatures are 65 bytes (r || s || v)")

    recovery_id = signature[64]
    if recovery_id >= 27:
        recovery_id -= 27

    normalized = key_api.Signature(signature_bytes=signature[:64] + bytes([recovery_id]))
    public_key = key_api.ecdsa_recover(_eip191_hash(MASTER_KEY_MESSAGE), normalized)
    return public_key.to_compressed_bytes()


def derive_legacy_signer_key(signature: "bytes | bytearray") -> bytes:
    """The compressed secp256k1 public key older T+ frontends registered as the signer.

    Derived from the identity signature rather than the wallet key itself. Current
    frontends register the wallet key (:func:`recover_signer_key`) and only fall back to
    this one, so it is a lookup path for existing accounts, not a target for new ones.

    Args:
        signature (bytes | bytearray): A signature over :data:`MASTER_KEY_MESSAGE`.

    Returns:
        bytes: The 33-byte compressed public key.
    """
    key_api = _require_eth_keys()
    seed = hashlib.sha512(bytes(signature)).digest()[SEED_SIZE : 2 * SEED_SIZE]
    return key_api.PrivateKey(seed).public_key.to_compressed_bytes()


class EvmDelegatedUser(DelegatedUser):
    """Act for a T+ account whose registered signer is an EVM wallet.

    ``account_public_key`` is the account id, as resolved by
    :meth:`tplus.client.base.BaseClient.resolve_evm_user`. Every request is co-signed by
    the wallet under EIP-191, which T+ verifies against the registered ``Secp256k1``
    signer. The wallet is prompted per signature; register an Ed25519 session signer with
    :meth:`tplus.client.orderbook.OrderBookClient.add_multisig_signer` and act through a
    plain :class:`~tplus.utils.user.DelegatedUser` to avoid that.

    Args:
        account_public_key: The T+ account id this user acts for.
        account: The wallet registered as a signer on that account.
        signer_key: The wallet's compressed secp256k1 public key. Recovered on first use
            when omitted, which costs one extra signature.
        sub_account: Optional sub-account index.
    """

    def __init__(
        self,
        account_public_key: "str | UserPublicKey",
        account: "EvmAccount",
        signer_key: bytes | None = None,
        sub_account: int | None = None,
    ) -> None:
        self._account_public_key = coerce_account_public_key(account_public_key)
        self._account = account
        self._signer_key = signer_key
        self._sub_account = sub_account
        self._evm_address = account.address

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.public_key} via {self._evm_address}>"

    @cached_property
    def signer_key(self) -> bytes:
        """The wallet's compressed secp256k1 public key, as registered on the account."""
        if self._signer_key is not None:
            return self._signer_key

        return recover_signer_key(sign_master_key_message(self._account))

    def sign(self, payload: str):
        raise ValueError(
            "Wallet-backed users cannot produce master signatures; use signing_parts() "
            "for request types that support additional signers."
        )

    def signing_parts(self, payload: str) -> tuple[list[int], list[AdditionalSigner]]:
        signature = sign_personal_message(self._account, compact_payload(payload))
        additional = AdditionalSigner(
            signer=SignerKey.secp256k1(list(self.signer_key)),
            signature=list(signature),
        )
        return [], [additional]
