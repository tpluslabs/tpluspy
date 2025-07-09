from eth_pydantic_types.hex.int import HexInt
from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.types import ChainID, UserPublicKey


class TxSettlementRequest(BaseModel):
    inner: "InnerSettlementRequest"
    signature: list[int]


class BaseInnerSettlementRequest(BaseModel):
    tplus_user: UserPublicKey
    """
    The settler.
    """

    asset_in: AssetIdentifier
    amount_in: HexInt
    asset_out: AssetIdentifier
    amount_out: HexInt

    chain_id: ChainID
    """
    The chain ID of the settlement (can settle cross-chain).
    """


class InnerSettlementRequest(BaseModel):
    """
    Inner settlement request part of atomic settlement.
    """

    calldata: list[HexInt]


class InnerBundleSettlementRequest(BaseInnerSettlementRequest):
    """
    Inner settlement request part of bundle settlement.
    """


class BundleSettlementRequest(BaseModel):
    inner: list["InnerBundleSettlementRequest"]
    bundle: "SimBundleRequest"
    signature: list[int]

    chain_id: ChainID
    """
    The chain ID of the deposit vault settling on.
    """


class SimBundleRequest(BaseModel):
    bundle: dict  # NOTE: Not using the model here so Ape isn't required.
    user: UserPublicKey
    bundle_id: int
