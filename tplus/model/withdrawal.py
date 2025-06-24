from typing import TYPE_CHECKING

from eth_pydantic_types.hex import HexInt, HexStr32
from pydantic import BaseModel, field_serializer

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.types import ChainID
from tplus.utils.bytes32 import to_bytes32
from tplus.utils.hex import str_to_vec

if TYPE_CHECKING:
    from tplus.utils.user import User


class InnerWithdrawalRequest(BaseModel):
    tplus_user: str
    asset: AssetIdentifier
    amount: HexInt
    target: HexStr32
    chain_id: ChainID

    @field_serializer("tplus_user", when_used="json")
    def serialize_vecs(self, user):
        return str_to_vec(user, size=32)


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
                    "target": to_bytes32(target).hex(),
                    "chain_id": chain_id,
                },
                "signature": [],
            }
        )
        model.signature = str_to_vec(signer.sign(model.signing_payload()).hex())
        return model

    def signing_payload(self) -> str:
        return (
            self.inner.model_dump_json(exclude_none=True)
            .replace(" ", "")
            .replace("\r", "")
            .replace("\n", "")
        )
