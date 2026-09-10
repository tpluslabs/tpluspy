"""Representation-rate mapping: which provider contract a token's rate is read from."""

import struct
from collections.abc import Callable, Sequence
from enum import Enum

from pydantic import BaseModel

from tplus.model.asset_identifier import Address32
from tplus.model.chain_address import ChainAddress
from tplus.model.council import CouncilEnvelope, CouncilSig, sign_council_payload


class RepresentationSourceKind(str, Enum):
    XSTOCKS_V2 = "XStocksV2"
    ONDO_SHARES_ORACLE = "OndoSharesOracle"

    def bincode(self) -> bytes:
        order = list(RepresentationSourceKind)
        return struct.pack("<I", order.index(self))


class RepresentationSource(BaseModel):
    kind: RepresentationSourceKind
    """Contract the rate is read from, on the same chain as the token the mapping keys it by."""
    provider_contract: Address32 | None = None

    def bincode(self) -> bytes:
        out = self.kind.bincode()
        if self.provider_contract is None:
            return out + b"\x00"

        return out + b"\x01" + bytes.fromhex(str(self.provider_contract).removeprefix("0x"))


class RepresentationOverride(BaseModel):
    source: RepresentationSource
    heartbeat_secs: int
    stale_after_secs: int

    def bincode(self) -> bytes:
        return (
            self.source.bincode()
            + struct.pack("<Q", self.heartbeat_secs)
            + struct.pack("<Q", self.stale_after_secs)
        )


class RepresentationRateMappingSnapshot(BaseModel):
    """Addresses that are not identity. Everything absent here converts one to one."""

    overrides: dict[ChainAddress, RepresentationOverride] = {}

    def bincode(self) -> bytes:
        # A BTreeMap serializes in ascending key order, so the bytes match on both sides.
        ordered = sorted(
            self.overrides, key=lambda token: bytes.fromhex(str(token).replace("@", ""))
        )
        out = struct.pack("<Q", len(ordered))
        for token in ordered:
            out += bytes(token) + self.overrides[token].bincode()

        return out


SET_REPRESENTATION_RATE_MAPPING_DOMAIN = b"tplus.ce.set_representation_rate_mapping.v1"


def bincode_mapping(mapping: RepresentationRateMappingSnapshot | None) -> bytes:
    """The council signs ``bincode(Option<RepresentationRateMappingSnapshot>)``."""
    if mapping is None:
        return b"\x00"

    return b"\x01" + mapping.bincode()


class SetRepresentationRateMappingPayload(CouncilEnvelope):
    mapping: RepresentationRateMappingSnapshot | None = None


class SetRepresentationRateMappingRequest(BaseModel):
    payload: SetRepresentationRateMappingPayload
    sigs: list[CouncilSig]

    @classmethod
    def signed(
        cls,
        mapping: RepresentationRateMappingSnapshot | None,
        envelope: CouncilEnvelope,
        signers: Sequence[str],
        sign: Callable[[str, bytes], str],
    ) -> "SetRepresentationRateMappingRequest":
        """A rotation the council has signed, over the encoding the clearing engine verifies."""
        sigs = sign_council_payload(
            envelope,
            SET_REPRESENTATION_RATE_MAPPING_DOMAIN,
            bincode_mapping(mapping),
            signers,
            sign,
        )
        return cls(
            payload=SetRepresentationRateMappingPayload(
                min_seq=envelope.min_seq,
                max_seq=envelope.max_seq,
                committee_hash=envelope.committee_hash,
                mapping=mapping,
            ),
            sigs=sigs,
        )
