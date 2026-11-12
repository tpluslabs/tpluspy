"""Representation rates: which provider contract a token's rate is read from, and its readings."""

from enum import Enum
from typing import Any

from eth_pydantic_types.hex.bytes import HexBytes32
from pydantic import BaseModel, ConfigDict, Field, field_validator

from tplus.model.asset_identifier import Address32
from tplus.model.chain_address import ChainAddress

DEFAULT_STALE_AFTER_SECS = 300
DEFAULT_MAX_RATE_JUMP_BPS = 1_000
REGISTRY_SOURCE_KINDS = {"XStocksV2": 1, "OndoSharesOracle": 2}


class RepresentationSourceKind(str, Enum):
    XSTOCKS_V2 = "XStocksV2"
    ONDO_SHARES_ORACLE = "OndoSharesOracle"

    @property
    def registry_kind(self) -> int:
        """The `sourceKind` the Registry stores for this kind."""
        return REGISTRY_SOURCE_KINDS[self.value]


class RepresentationSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: RepresentationSourceKind
    """Contract the rate is read from, on the same chain as the token the mapping keys it by."""
    provider_contract: Address32 | None = None


class RegistryRepresentationConfig(BaseModel):
    """Mirror of `Registry.RepresentationConfig`; all zeros removes a token's config."""

    model_config = ConfigDict(populate_by_name=True)

    provider_contract: HexBytes32 = Field(
        default=HexBytes32(b"\x00" * 32), alias="providerContract"
    )
    """The contract the rate is read from, on the token's chain and encoded like its token
    address (left-aligned on EVM chains, or the token is unavailable); required for kind 2."""

    stale_after_secs: int = Field(default=DEFAULT_STALE_AFTER_SECS, alias="staleAfterSecs")
    """Age past which a rate stops converting; more than 60, or the token is unavailable."""

    max_rate_jump_bps: int = Field(default=DEFAULT_MAX_RATE_JUMP_BPS, alias="maxRateJumpBps")
    """Largest move a read may report before the token is quarantined, 1 to 4999 basis points."""

    source_kind: int = Field(alias="sourceKind")
    """0 unset (the token converts 1:1), 1 xStocks v2, 2 Ondo shares oracle."""

    @classmethod
    def removed(cls) -> "RegistryRepresentationConfig":
        return cls(staleAfterSecs=0, maxRateJumpBps=0, sourceKind=0)

    @classmethod
    def from_struct(cls, struct: Any) -> "RegistryRepresentationConfig":
        """Parse the decoded `Registry.RepresentationConfig` struct of either EVM backend."""
        return cls.model_validate(struct, from_attributes=True)


class RepresentationRateHealth(str, Enum):
    """Whether the clearing engine is converting a token, and why not when it is not."""

    CONVERTING = "Converting"
    UNREAD = "Unread"
    STALE = "Stale"
    REFUSED = "Refused"
    QUARANTINED = "Quarantined"
    AWAITING_REGISTRY = "AwaitingRegistry"
    INVALID_CONFIG = "InvalidConfig"

    def converts(self) -> bool:
        return self is RepresentationRateHealth.CONVERTING


class PreviewUnavailable(str, Enum):
    """Why a preview names no representation amount."""

    AWAITING_REGISTRY = "AWAITING_REGISTRY"
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
