from typing import TYPE_CHECKING

from eth_pydantic_types.hex import HexInt
from pydantic import BaseModel, field_serializer

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.types import ChainID, UserPublicKey
from tplus.utils.hex import str_to_vec

if TYPE_CHECKING:
    from tplus.utils.user import User


class InnerWithdrawalRequest(BaseModel):
    tplus_user: UserPublicKey
    asset: AssetIdentifier
    amount: HexInt
    chain_id: ChainID

    def signing_payload(self) -> str:
        return self.model_dump_json(exclude_none=True)

    @field_serializer("amount")
    def serialize_amount(self, value: HexInt) -> str:
        return hex(value)[2:]


class WithdrawalRequest(BaseModel):
    inner: InnerWithdrawalRequest
    signature: list[int]

    @classmethod
    def create_signed(
        cls,
        signer: "User",
        asset: AssetIdentifier | str,
        amount: int,
        chain_id: int,
    ) -> "WithdrawalRequest":
        if not isinstance(asset, AssetIdentifier):
            if asset.startswith("0x") and "@" not in asset:
                # Helper to automatically include the chain.
                asset = f"{asset}@{chain_id}"

            asset = AssetIdentifier.model_validate(asset)

        inner = InnerWithdrawalRequest.model_validate(
            {
                "tplus_user": signer.public_key,
                "asset": asset,
                "amount": amount,
                "chain_id": chain_id,
            }
        )
        signature = str_to_vec(signer.sign(inner.signing_payload()).hex())
        return cls(inner=inner, signature=signature)

    def signing_payload(self) -> str:
        return self.inner.signing_payload()
