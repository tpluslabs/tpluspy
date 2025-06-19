from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier


class InnerWithdrawalRequest(BaseModel):
    tplus_user: str
    asset: AssetIdentifier
    amount: int
    target: str
    chain_id: int


class WithdrawalRequest(BaseModel):
    inner: InnerWithdrawalRequest
    signature: list[int]
