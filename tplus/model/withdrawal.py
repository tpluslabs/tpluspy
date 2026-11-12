from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, field_serializer

from tplus.model.asset_identifier import Address32, AssetAddress, AssetIdentifier
from tplus.model.multisig import AdditionalSigner
from tplus.model.types import UserPublicKey
from tplus.utils.user import to_user

if TYPE_CHECKING:
    from tplus.types import UserLike


class InnerWithdrawalRequest(BaseModel):
    tplus_user: UserPublicKey
    asset: AssetAddress
    amount: int
    nonce: int | None = None
    target: Address32 = Address32("00" * 32)
    max_fee: int | None = None
    """
    The most the withdrawal may reserve for its rebalancing fee, in canonical (1e18) units of
    ``asset``: ``None`` accepts the protocol-calculated reservation, ``0`` only a fee-free
    approval. Signed with the request, ``null`` included.
    """

    def signing_payload(self) -> str:
        return self.model_dump_json()

    @field_serializer("amount")
    def serialize_amount(self, value: int) -> str:
        return str(value)

    @field_serializer("max_fee")
    def serialize_max_fee(self, value: int | None) -> str | None:
        return None if value is None else str(value)


class WithdrawalRequest(BaseModel):
    inner: InnerWithdrawalRequest
    signature: list[int]
    additional_signers: list[AdditionalSigner] = []

    @classmethod
    def create_signed(
        cls,
        signer: "UserLike",
        asset: AssetAddress | str,
        amount: int,
        nonce: int | None = None,
        target: Address32 | str | None = None,
        max_fee: int | None = None,
    ) -> "WithdrawalRequest":
        signer = to_user(signer)
        if isinstance(asset, str):
            asset = AssetIdentifier.model_validate(asset)
        elif not isinstance(asset, AssetAddress):
            raise TypeError(
                f"asset must be an AssetAddress (address@chain), got {type(asset).__name__}."
            )

        data: dict = {
            "tplus_user": signer.public_key,
            "asset": asset,
            "amount": amount,
        }
        if nonce is not None:
            data["nonce"] = nonce
        if target is not None:
            data["target"] = target
        if max_fee is not None:
            data["max_fee"] = max_fee

        inner = InnerWithdrawalRequest.model_validate(data)
        signature, additional_signers = signer.signing_parts(inner.signing_payload())
        return cls(inner=inner, signature=signature, additional_signers=additional_signers)

    def signing_payload(self) -> str:
        return self.inner.signing_payload()


class InnerCancelTransferRequest(BaseModel):
    user: UserPublicKey
    source: int = Field(gt=0)
    token: AssetAddress
    nonce: int

    def signing_payload(self) -> str:
        return self.model_dump_json()


class CancelTransferRequest(BaseModel):
    inner: InnerCancelTransferRequest
    signature: list[int]
    additional_signers: list[AdditionalSigner] = []

    @classmethod
    def create_signed(
        cls,
        signer: "UserLike",
        source: int,
        token: AssetAddress | str,
        nonce: int,
    ) -> "CancelTransferRequest":
        signer = to_user(signer)
        if not isinstance(token, AssetAddress):
            token = AssetAddress.model_validate(token)

        inner = InnerCancelTransferRequest(
            user=signer.public_key,
            source=source,
            token=token,
            nonce=nonce,
        )
        signature, additional_signers = signer.signing_parts(inner.signing_payload())
        return cls(inner=inner, signature=signature, additional_signers=additional_signers)

    def signing_payload(self) -> str:
        return self.inner.signing_payload()


class InnerResumeWithdrawalsRequest(BaseModel):
    # Field order is the signed preimage; keep it aligned with the Rust struct.
    user: UserPublicKey  # signer
    target_user: UserPublicKey
    nonce: int

    def signing_payload(self) -> str:
        return self.model_dump_json()


class ResumeWithdrawalsRequest(BaseModel):
    inner: InnerResumeWithdrawalsRequest
    signature: list[int]
    additional_signers: list[AdditionalSigner] = []

    @classmethod
    def create_signed(
        cls,
        signer: "UserLike",
        target_user: UserPublicKey | str,
        nonce: int,
    ) -> "ResumeWithdrawalsRequest":
        signer = to_user(signer)
        inner = InnerResumeWithdrawalsRequest(
            user=signer.public_key,
            target_user=UserPublicKey(target_user),
            nonce=nonce,
        )
        signature, additional_signers = signer.signing_parts(inner.signing_payload())
        return cls(inner=inner, signature=signature, additional_signers=additional_signers)

    def signing_payload(self) -> str:
        return self.inner.signing_payload()


class WithdrawalDelayParameters(BaseModel):
    min_delay: int = Field(alias="minDelay")
    max_delay: int = Field(alias="maxDelay")
    delay_clamps: list[int] = Field(alias="delayClamps")
    delay_values: list[int] = Field(alias="delayValues")
    cap_floor: int = Field(default=50_000, alias="capFloor")

    model_config = {"populate_by_name": True}


class TransferDelayed(BaseModel):
    type: Literal["delayed"]
    execution_time_ns: int


class TransferFilling(BaseModel):
    type: Literal["filling"]
    fillable_since_ns: int


class QueuedTransfer(BaseModel):
    user: UserPublicKey
    source_index: int
    token: AssetAddress
    nonce: int
    requested_principal: str
    filled_principal: str
    status: TransferDelayed | TransferFilling = Field(discriminator="type")
