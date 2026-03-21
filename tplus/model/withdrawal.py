from typing import TYPE_CHECKING

from eth_pydantic_types.hex import HexInt
from pydantic import BaseModel, Field, field_serializer

from tplus.model.asset_identifier import AssetAddress, AssetIdentifier
from tplus.model.types import ChainID, UserPublicKey
from tplus.utils.hex import str_to_vec

if TYPE_CHECKING:
    from tplus.utils.user import User


class InnerWithdrawalRequest(BaseModel):
    tplus_user: UserPublicKey
    asset: AssetAddress
    amount: HexInt

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
        asset: AssetAddress | str,
        amount: int,
        chain_id: ChainID | str | None = None,
    ) -> "WithdrawalRequest":
        if not isinstance(asset, AssetAddress):
            if asset.startswith("0x") and "@" not in asset:
                if chain_id is None:
                    raise ValueError("chain_id is required when asset does not include chain.")

                # Helper to automatically include the chain.
                asset = f"{asset}@{chain_id}"

            asset = AssetIdentifier.model_validate(asset)

        inner = InnerWithdrawalRequest.model_validate(
            {
                "tplus_user": signer.public_key,
                "asset": asset,
                "amount": amount,
            }
        )
        signature = str_to_vec(signer.sign(inner.signing_payload()).hex())
        return cls(inner=inner, signature=signature)

    def signing_payload(self) -> str:
        return self.inner.signing_payload()


class WithdrawalDelayParameters(BaseModel):
    min_delay: int = Field(alias="minDelay")
    max_delay: int = Field(alias="maxDelay")
    delay_clamps: list[int] = Field(alias="delayClamps")
    delay_values: list[int] = Field(alias="delayValues")
