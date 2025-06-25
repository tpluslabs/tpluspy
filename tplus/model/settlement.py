from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.types import ChainID, UserPublicKey


class TxSettlementRequest(BaseModel):
    inner: "InnerSettlementRequest"
    signature: list[int]


class InnerSettlementRequest(BaseModel):
    tplus_user: UserPublicKey
    calldata: list[int]
    asset_in: AssetIdentifier
    amount_in: int
    asset_out: AssetIdentifier
    amount_out: int
    chain_id: ChainID


class BundleSettlementRequest(BaseModel):
    inner: list["InnerSettlementRequest"]
    bundle: "SimBundleRequest"
    signature: list[int]
    chain_id: ChainID


class SimBundleRequest(BaseModel):
    bundle: dict  # NOTE: Not using the model here so Ape isn't required.
    user: UserPublicKey
    bundle_id: int
