import json
from typing import TYPE_CHECKING

from eth_pydantic_types.address import Address
from eth_pydantic_types.hex.int import HexInt
from pydantic import BaseModel, field_serializer

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.types import ChainID, UserPublicKey
from tplus.utils.decimals import normalize_to_inventory
from tplus.utils.hex import str_to_vec

if TYPE_CHECKING:
    from tplus.utils.user import User


class BaseSettlement(BaseModel):
    """
    The shared fields for all inner settlement requests.
    """

    asset_in: AssetIdentifier
    amount_in: HexInt
    asset_out: AssetIdentifier
    amount_out: HexInt

    @field_serializer("amount_in", "amount_out")
    def serialize_amounts(self, val):
        return hex(val)[2:]


class InnerSettlementRequest(BaseSettlement):
    """
    Atomic settlement inner request.
    """

    tplus_user: UserPublicKey
    chain_id: ChainID

    @classmethod
    def from_raw(
        cls,
        asset_in: AssetIdentifier,
        amount_in: int,
        decimals_in: int,
        asset_out: AssetIdentifier,
        amount_out: int,
        decimals_out: int,
        tplus_user: UserPublicKey,
        chain: ChainID,
    ) -> "InnerSettlementRequest":
        """
        Create a request using raw amounts by first normalizing them to the CE.

        Args:

        """
        return cls(
            asset_in=asset_in,
            amount_in=normalize_to_inventory(amount_in, decimals_in, "up"),
            asset_out=asset_out,
            amount_out=normalize_to_inventory(amount_out, decimals_out, "down"),
            tplus_user=tplus_user,
            chain_id=chain,
        )

    def signing_payload(self) -> str:
        base_data = self.model_dump(mode="json", exclude_none=True)

        user = base_data.pop("tplus_user")
        chain_id = base_data.pop("chain_id", None)

        # NOTE: The order here matters!
        payload = {
            "tplus_user": user,
            **base_data,
            "chain_id": chain_id,
        }

        return json.dumps(payload, separators=(",", ":"))


class TxSettlementRequest(BaseModel):
    """
    Atomic settlement request.
    """

    inner: InnerSettlementRequest
    """
    The inner part of the request (signature fields).
    """

    signature: list[int]
    """
    The settler's signature from signing the necessary data (mostly from ``.inner``).
    """

    @classmethod
    def create_signed(
        cls,
        inner: InnerSettlementRequest | dict,
        signer: "User",
    ) -> "TxSettlementRequest":
        """
        Create and sign a settlement request.

        Args:
            inner (:class:`~tplus.model.settlement.InnerSettlementRequest`): The inner part of
              the request (signature fields).
            signer:
            signer (:class:`~tplus.utils.user.model.User`): The tplus user signing.
        """

        if isinstance(inner, dict):
            if "tplus_user" not in inner:
                inner["tplus_user"] = signer.public_key

            inner = InnerSettlementRequest.model_validate(inner)

        signature = str_to_vec(signer.sign(inner.signing_payload()).hex())
        return cls(inner=inner, signature=signature)

    def signing_payload(self) -> str:
        return self.inner.signing_payload()


class BatchSettlementRequest(BaseModel):
    """
    Batch settlement request.
    """

    inner: "InnerBatchSettlementRequest"
    """
    The inner part of the request (signature fields).
    Allows multiple settlements, unlike ``TxSettlementRequest``.
    """

    signature: list[int]
    """
    The settler's signature from signing the necessary data (mostly from ``.inner``).
    """

    @classmethod
    def create_signed(
        cls, inner: "InnerBatchSettlementRequest", signer: "User"
    ) -> "BatchSettlementRequest":
        signature = str_to_vec(signer.sign(inner.signing_payload()).hex())
        return cls(inner=inner, signature=signature)

    def signing_payload(self) -> str:
        return self.inner.signing_payload()


class InnerBatchSettlementRequest(BaseModel):
    """
    Batch settlement inner request. Does not contain any additional fields.
    """

    settlements: list[BaseSettlement]
    """
    All settlement included in the transaction bundle.
    """

    bundle: dict
    """
    The bundle that gets sent to the blockchain client process.
    """

    chain_id: ChainID
    """
    The chain settling on.
    """

    tplus_user: UserPublicKey
    """
    The settler.
    """

    target_address: Address
    """
    Target address, needed so we can create the settlement transactions.
    """

    pull_batch_settlement_gas: int
    """
    The amount of gas to use for the `pullBatchSettlement()` call.
    """

    push_batch_settlements_gas: int
    """
    The amount of gas to use for the `pushBatchSettlements()` call.
    """

    def signing_payload(self) -> str:
        return (
            self.model_dump_json(exclude_none=True)
            .replace(" ", "")
            .replace("\r", "")
            .replace("\n", "")
        )
