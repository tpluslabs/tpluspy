from typing import TYPE_CHECKING

from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier
from tplus.utils.hex import str_to_vec

if TYPE_CHECKING:
    from tplus.utils.user import User


class InnerWithdrawalRequest(BaseModel):
    tplus_user: str
    asset: AssetIdentifier
    amount: int
    target: str
    chain_id: int


class WithdrawalRequest(BaseModel):
    inner: InnerWithdrawalRequest
    signature: list[int]

    @classmethod
    def create_signed(
        cls,
        tplus_user: str,
        asset: AssetIdentifier,
        amount: int,
        target: str,
        chain_id: int,
        signer: "User",
    ) -> "WithdrawalRequest":
        model = cls.model_validate(
            {
                "inner": {
                    "tplus_user": tplus_user,
                    "asset": asset,
                    "amount": amount,
                    "target": target,
                    "chain_id": chain_id,
                },
                "signature": [],
            }
        )
        model.signature = str_to_vec(signer.sign(model.inner.model_dump_json()).hex())
        return model
