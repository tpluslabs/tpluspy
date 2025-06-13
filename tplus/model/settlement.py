from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier


class TxSettlementRequest(BaseModel):
    inner: "InnerSettlementRequest"
    signature: list[int]


class InnerSettlementRequest(BaseModel):
    tplus_user: str
    calldata: list[int]
    asset_in: AssetIdentifier
    amount_in: int
    asset_out: AssetIdentifier
    amount_out: int
    chain_id: int


class BundleSettlementRequest(BaseModel):
    inner: list["InnerSettlementRequest"]
    bundle: "SimBundleRequest"
    signature: list[int]
    chain_id: int


class SimBundleRequest(BaseModel):
    bundle: dict  # NOTE: Not using the model here so Ape isn't required.
    user: list[int]
    bundle_id: int
