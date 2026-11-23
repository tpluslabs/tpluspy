"""Oracle configs as the Registry stores them: the sources an asset is priced from."""

from enum import IntEnum
from typing import Any

from eth_pydantic_types.hex.bytes import HexBytes32
from eth_utils import keccak
from pydantic import BaseModel, ConfigDict, Field

from tplus.model.registry_asset import RegistryChainId

HOSTNAME_TLS_IDENTITY_KIND = 1
"""The `kind` of a hostname commitment, the only TLS identity kind."""

DEFAULT_RECEIPT_VALIDITY_SECS = 30
DEFAULT_CANONICAL_STALENESS_SECS = 60


class OracleSourceKind(IntEnum):
    """The `sourceKind` the Registry stores for each price source."""

    PYTH = 1
    HYPERLIQUID = 3
    BINANCE = 4
    PYTH_LAZER = 5


class OracleValidityKind(IntEnum):
    """How long an observation of a source stays usable."""

    CONTINUOUS = 1
    """Observation age within `validitySecs`."""

    HEARTBEAT = 2
    """Provider observation within its heartbeat `validitySecs` plus `validityGraceSecs`."""

    RECEIPT_TIME = 4
    """Age of the last authenticated response within `validitySecs`, for sources whose
    prices carry no timestamp."""


def compute_hostname_commitment(hostname: str) -> bytes:
    """`keccak256` of the lowercase hostname: the Registry does not lowercase it."""
    return keccak(hostname.lower().encode())


def to_symbol_feed_id(symbol: str) -> bytes:
    """A venue symbol (Hyperliquid, Binance) as `feedId`: ASCII, left-aligned, zero-padded."""
    encoded = symbol.encode("ascii")
    if not encoded or len(encoded) > 32 or not all(0x21 <= byte <= 0x7E for byte in encoded):
        raise ValueError(f"{symbol!r} cannot be a feed id")

    return encoded.ljust(32, b"\x00")


class RegistryOracleTlsIdentity(BaseModel):
    """Mirror of `Registry.OracleTlsIdentity`: a host the source may be fetched from."""

    model_config = ConfigDict(populate_by_name=True)

    kind: int = HOSTNAME_TLS_IDENTITY_KIND
    identity: HexBytes32

    @classmethod
    def hostname(cls, hostname: str) -> "RegistryOracleTlsIdentity":
        return cls(identity=HexBytes32(compute_hostname_commitment(hostname)))


class RegistryOracleSourceConfig(BaseModel):
    """Mirror of `Registry.OracleSourceConfig`."""

    model_config = ConfigDict(populate_by_name=True)

    source_kind: int = Field(alias="sourceKind")
    feed_id: HexBytes32 = Field(alias="feedId")
    active: bool = True
    tls_identities: list[RegistryOracleTlsIdentity] = Field(alias="tlsIdentities")
    chain_id: RegistryChainId = Field(default=RegistryChainId(routingId=0, vmId=0), alias="chainId")
    """Only read for onchain sources."""

    units_per_contract: int = Field(default=1, alias="unitsPerContract")
    """How many units one listing quotes (1000 for `kPEPE`); Hyperliquid only."""

    validity_kind: int = Field(alias="validityKind")
    validity_secs: int = Field(alias="validitySecs")
    validity_grace_secs: int = Field(default=0, alias="validityGraceSecs")
    """Only a heartbeat validity takes a grace."""

    @classmethod
    def hyperliquid(
        cls,
        coin: str,
        hostname: str,
        *,
        units_per_contract: int = 1,
        validity_secs: int = DEFAULT_RECEIPT_VALIDITY_SECS,
    ) -> "RegistryOracleSourceConfig":
        """Hyperliquid's oracle price of `coin`, fetched from `hostname`."""
        return cls(
            sourceKind=OracleSourceKind.HYPERLIQUID,
            feedId=HexBytes32(to_symbol_feed_id(coin)),
            tlsIdentities=[RegistryOracleTlsIdentity.hostname(hostname)],
            unitsPerContract=units_per_contract,
            validityKind=OracleValidityKind.RECEIPT_TIME,
            validitySecs=validity_secs,
        )


class RegistryOracleConfig(BaseModel):
    """Mirror of `Registry.OracleConfig`; no sources unconfigures the asset."""

    model_config = ConfigDict(populate_by_name=True)

    sources: list[RegistryOracleSourceConfig]
    min_sources: int = Field(default=1, alias="minSources")
    price_decimals: int = Field(alias="priceDecimals")
    """The scale the oracle reports this asset's price at."""

    max_deviation_bps: int = Field(default=0, alias="maxDeviationBps")
    canonical_staleness_secs: int = Field(
        default=DEFAULT_CANONICAL_STALENESS_SECS, alias="canonicalStalenessSecs"
    )

    @classmethod
    def unconfigured(cls) -> "RegistryOracleConfig":
        return cls(sources=[], priceDecimals=0)

    @classmethod
    def from_struct(cls, struct: Any) -> "RegistryOracleConfig":
        """Parse the decoded `Registry.OracleConfig` struct of either EVM backend."""
        return cls.model_validate(struct, from_attributes=True)
