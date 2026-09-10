"""Council k-of-n multisig envelope shared by the clearing engine's rotation endpoints."""

import hashlib
from collections.abc import Callable, Sequence

from pydantic import BaseModel


class CouncilSig(BaseModel):
    signer: str
    signature: str


class CouncilEnvelope(BaseModel):
    """Replay window and committee a council payload is signed against."""

    min_seq: int
    max_seq: int
    committee_hash: str


def committee_hash(council_pubkeys: Sequence[str], k: int) -> bytes:
    hasher = hashlib.sha256()
    for pubkey in sorted(pubkey.lower() for pubkey in council_pubkeys):
        hasher.update(pubkey.encode("ascii"))

    hasher.update(k.to_bytes(8, "big"))
    return hasher.digest()


def council_digest(envelope: CouncilEnvelope, domain: bytes, value: bytes) -> bytes:
    """The SHA256 each council member signs, over the domain-separated payload."""
    signed = envelope.min_seq.to_bytes(8, "big")
    signed += envelope.max_seq.to_bytes(8, "big")
    signed += bytes.fromhex(envelope.committee_hash)
    signed += len(domain).to_bytes(8, "big") + domain
    signed += len(value).to_bytes(8, "big") + value
    return hashlib.sha256(signed).digest()


def sign_council_payload(
    envelope: CouncilEnvelope,
    domain: bytes,
    value: bytes,
    signers: Sequence[str],
    sign: Callable[[str, bytes], str],
) -> list[CouncilSig]:
    """Signatures over ``value``, one per signer.

    Args:
        sign: Holds the key material and returns compact low-S secp256k1 hex.
    """
    digest = council_digest(envelope, domain, value)
    return [CouncilSig(signer=signer, signature=sign(signer, digest)) for signer in signers]
