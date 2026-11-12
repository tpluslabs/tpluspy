from eth_pydantic_types.hex.bytes import HexBytes32
from pydantic import BaseModel, ConfigDict, Field


class RegistryChainId(BaseModel):
    """Mirror of `Registry.ChainId` from tplus-contracts."""

    model_config = ConfigDict(populate_by_name=True)

    routing_id: int = Field(alias="routingId")
    """The routing ID, e.g. 0 for EVM-style chains."""

    vm_id: int = Field(alias="vmId")
    """The chain's ID within its routing ID, e.g. the EVM chain ID."""


class AssetData(BaseModel):
    """Mirror of `Registry.AssetData` from tplus-contracts."""

    model_config = ConfigDict(populate_by_name=True)

    index: int
    """The asset's Registry index."""

    asset_address: HexBytes32 = Field(alias="assetAddress")
    """The asset's address, as bytes32 so non-EVM chains fit."""

    chain_id: RegistryChainId = Field(alias="chainId")
    """The chain the asset lives on."""

    max_deposits: int = Field(alias="maxDeposits")
    """Cap on deposits (collateral cap)."""

    max_1hr_deposits: int = Field(alias="max1hrDeposits")
    """Cap on fungible deposits over one hour."""

    min_weight: int = Field(alias="minWeight")
    """Raw weight value (not percentage)."""
