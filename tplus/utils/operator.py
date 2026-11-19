"""secp256k1 operator signing, used by the blockchain-client and CE admin endpoints."""

import hashlib
from collections.abc import Callable
from functools import partial

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed, decode_dss_signature
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
SECP256K1_HALF_ORDER = SECP256K1_ORDER // 2


def load_operator_sk(operator_secret: str) -> ec.EllipticCurvePrivateKey:
    secret_bytes = bytes.fromhex(operator_secret)
    return ec.derive_private_key(int.from_bytes(secret_bytes, "big"), ec.SECP256K1())


def compute_operator_public_key(sk: ec.EllipticCurvePrivateKey) -> str:
    """The compressed public key hex the CE names a signer by."""
    return sk.public_key().public_bytes(Encoding.X962, PublicFormat.CompressedPoint).hex()


def load_operator_signers(operator_secrets: list[str]) -> dict[str, Callable[[bytes], str]]:
    """Digest signers keyed by their compressed public key hex."""
    keys = [load_operator_sk(secret) for secret in operator_secrets]
    return {compute_operator_public_key(key): partial(sign_operator_digest, sk=key) for key in keys}


def sign_operator_payload(payload: bytes, sk: ec.EllipticCurvePrivateKey) -> str:
    """SHA256 -> ECDSA sign -> low-S normalize -> compact r||s -> hex."""
    return sign_operator_digest(hashlib.sha256(payload).digest(), sk)


def sign_operator_digest(digest: bytes, sk: ec.EllipticCurvePrivateKey) -> str:
    sig_der = sk.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))
    r, s = decode_dss_signature(sig_der)
    if s > SECP256K1_HALF_ORDER:
        s = SECP256K1_ORDER - s

    return (r.to_bytes(32, "big") + s.to_bytes(32, "big")).hex()
