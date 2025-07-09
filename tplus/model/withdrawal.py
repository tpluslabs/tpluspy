from typing import TYPE_CHECKING

from eth_pydantic_types.hex import HexInt, HexStr32
from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.types import ChainID, UserPublicKey
from tplus.utils.hex import str_to_vec

if TYPE_CHECKING:
    from tplus.utils.user import User


class InnerWithdrawalRequest(BaseModel):
    tplus_user: UserPublicKey
    asset: AssetIdentifier
    amount: HexInt
    target: HexStr32
    chain_id: ChainID

    def signing_payload(self) -> str:
        return (
            self.model_dump_json(exclude_none=True)
            .replace(" ", "")
            .replace("\r", "")
            .replace("\n", "")
        )


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
        inner = InnerWithdrawalRequest(
            tplus_user=tplus_user,
            asset=asset,
            amount=amount,
            target=target,
            chain_id=chain_id,
        )
        signature = str_to_vec(signer.sign(inner.signing_payload()).hex())
        return cls(inner=inner, signature=signature)

    def signing_payload(self) -> str:
        return self.inner.signing_payload()
