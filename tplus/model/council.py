"""Council k-of-n multisig envelope shared by the clearing engine's rotation endpoints."""

import hashlib
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, SerializeAsAny


class CouncilSig(BaseModel):
    signer: str
    signature: str


class CouncilEnvelope(BaseModel):
    """Replay window and committee a council payload is signed against."""

    min_seq: int
    max_seq: int
    committee_hash: str


PayloadT = TypeVar("PayloadT", bound=CouncilEnvelope)


class CouncilRequest(BaseModel, Generic[PayloadT]):
    payload: SerializeAsAny[PayloadT]
    sigs: list[CouncilSig]


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


def build_council_request(
    payload_type: type[PayloadT],
    fields: dict[str, Any],
    domain: bytes,
    value: bytes,
    signers: Mapping[str, Callable[[bytes], str]],
    threshold: int,
    min_seq: int,
    max_seq: int,
) -> CouncilRequest[PayloadT]:
    """A council-signed request whose payload carries ``fields`` beside the envelope.

    Args:
        signers: Digest signers keyed by compressed public key hex, together the committee.
    """
    envelope = CouncilEnvelope(
        min_seq=min_seq,
        max_seq=max_seq,
        committee_hash=committee_hash(list(signers), threshold).hex(),
    )
    sigs = sign_council_payload(
        envelope, domain, value, list(signers), lambda signer, digest: signers[signer](digest)
    )
    return CouncilRequest(payload=payload_type(**envelope.model_dump(), **fields), sigs=sigs)
