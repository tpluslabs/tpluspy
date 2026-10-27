"""Representation-rate mapping: which provider contract a token's rate is read from."""

import struct
from collections.abc import Callable, Sequence
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator

from tplus.model.asset_identifier import Address32
from tplus.model.chain_address import ChainAddress
from tplus.model.council import CouncilEnvelope, CouncilSig, sign_council_payload

DEFAULT_HEARTBEAT_SECS = 30
DEFAULT_STALE_AFTER_SECS = 300
DEFAULT_MAX_RATE_JUMP_BPS = 1_000


class RepresentationSourceKind(str, Enum):
    XSTOCKS_V2 = "XStocksV2"
    ONDO_SHARES_ORACLE = "OndoSharesOracle"

    def bincode(self) -> bytes:
        order = list(RepresentationSourceKind)
        return struct.pack("<I", order.index(self))


class RepresentationSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: RepresentationSourceKind
    """Contract the rate is read from, on the same chain as the token the mapping keys it by."""
    provider_contract: Address32 | None = None

    def bincode(self) -> bytes:
        out = self.kind.bincode()
        if self.provider_contract is None:
            return out + b"\x00"

        return out + b"\x01" + bytes.fromhex(str(self.provider_contract).removeprefix("0x"))


class RepresentationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: RepresentationSource
    heartbeat_secs: int
    stale_after_secs: int
    max_rate_jump_bps: int

    def bincode(self) -> bytes:
        return (
            self.source.bincode()
            + struct.pack("<Q", self.heartbeat_secs)
            + struct.pack("<Q", self.stale_after_secs)
            + struct.pack("<I", self.max_rate_jump_bps)
        )


class RepresentationRateMappingSnapshot(BaseModel):
    """Addresses that are not identity. Everything absent here converts one to one."""

    model_config = ConfigDict(extra="forbid")

    representations: dict[ChainAddress, RepresentationConfig] = {}

    def bincode(self) -> bytes:
        # A BTreeMap serializes in ascending key order, so the bytes match on both sides.
        ordered = sorted(
            self.representations, key=lambda token: bytes.fromhex(str(token).replace("@", ""))
        )
        out = struct.pack("<Q", len(ordered))
        for token in ordered:
            out += bytes(token) + self.representations[token].bincode()

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


class RepresentationRateHealth(str, Enum):
    """Whether the clearing engine is converting a token, and why not when it is not."""

    CONVERTING = "Converting"
    UNREAD = "Unread"
    STALE = "Stale"
    REFUSED = "Refused"
    QUARANTINED = "Quarantined"
    MAPPING_CLEARED = "MappingCleared"

    def converts(self) -> bool:
        return self is RepresentationRateHealth.CONVERTING


class PreviewUnavailable(str, Enum):
    """Why a preview names no representation amount."""

    MAPPING_CLEARED = "MAPPING_CLEARED"
    RATE_UNHEALTHY = "RATE_UNHEALTHY"
    DECIMALS_UNKNOWN = "DECIMALS_UNKNOWN"
    ROUNDS_TO_ZERO = "ROUNDS_TO_ZERO"


class RateActivation(str, Enum):
    """Whether a clock or the provider's own next read puts the pending rate into effect."""

    AT_SECONDS = "AtSeconds"
    PROVIDER_APPLIED = "ProviderApplied"


class PendingRate(BaseModel):
    """Rate a provider has announced but the clearing engine is not converting at yet."""

    canonical_per_representation: int
    activation: RateActivation
    effective_at_secs: int | None = None

    @field_validator("activation", mode="before")
    @classmethod
    def _name_the_variant(cls, value: object) -> object:
        """`AtSeconds` arrives as `{"AtSeconds": <secs>}`, whose seconds `effective_at_secs` holds."""
        if isinstance(value, dict) and len(value) == 1:
            return next(iter(value))

        return value


class RepresentationRate(BaseModel):
    """Rate one token converts at, as the clearing engine applies it."""

    health: RepresentationRateHealth
    unhealthy_reason: str | None = None
    canonical_per_representation: int | None = None
    source: RepresentationSource | None = None
    observed_at_secs: int | None = None
    age_secs: int | None = None
    pending: PendingRate | None = None


class RepresentationRatesResponse(BaseModel):
    """`GET /registry/representation-rates`."""

    state_id: str
    mapping_id: str | None = None
    default_state: RepresentationRate
    representations: dict[ChainAddress, RepresentationRate] = {}


class RepresentationPreviewResponse(BaseModel):
    """Token-out leg of a withdrawal or settlement, as the clearing engine would round it."""

    asset: ChainAddress
    state_id: str
    health: RepresentationRateHealth
    approval_available: bool
    unavailable_reason: PreviewUnavailable | None = None
    token_decimals: int | None = None
    canonical_amount: int
    canonical_per_representation: int | None = None
    representation_amount: int | None = None
    chain_amount: int | None = None
    representation_remainder: int | None = None
    canonical_remainder: int | None = None
