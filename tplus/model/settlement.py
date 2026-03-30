import json
from typing import TYPE_CHECKING, Literal

from eth_pydantic_types.hex.int import HexInt
from pydantic import BaseModel, field_serializer

from tplus.model.asset_identifier import Address32, AssetAddress
from tplus.model.types import ChainID, UserPublicKey
from tplus.utils.decimals import to_inventory_decimals
from tplus.utils.hex import str_to_vec

if TYPE_CHECKING:
    from tplus.utils.user import User


class BaseSettlement(BaseModel):
    """
    The shared fields for all inner settlement requests.
    """

    mode: Literal["margin", "spot"] = "margin"
    asset_in: Address32
    amount_in: HexInt
    asset_out: Address32
    amount_out: HexInt

    @field_serializer("amount_in", "amount_out")
    def serialize_amounts(self, val):
        return hex(val)[2:]


class InnerSettlementRequest(BaseSettlement):
    """
    Atomic settlement inner request.
    """

    tplus_user: UserPublicKey
    sub_account_index: int
    settler: UserPublicKey
    chain_id: ChainID

    @classmethod
    def from_raw(
        cls,
        asset_in: Address32 | str,
        amount_in: int,
        decimals_in: int,
        asset_out: AssetAddress | str,
        amount_out: int,
        decimals_out: int,
        tplus_user: UserPublicKey,
        chain: ChainID | str,
        sub_account_index: int,
        settler: UserPublicKey | None = None,
        mode: "Literal['margin', 'spot']" = "margin",
    ) -> "InnerSettlementRequest":
        """
        Create a request using raw amounts by first normalizing them to the CE.

        Args:
            asset_in (:class:`~tplus.models.asset_identifier.Address32 | str): The asset being provided into the
              protocol.
            amount_in (int): The raw on-chain integer amount of the input asset (before adjusting for decimals).
            decimals_in (int): The number of decimal places for the input asset.
            asset_out (:class:`~tplus.models.asset_identifier.Address32 | str): The asset expected to be received from
              the protocol.
            amount_out (int): The raw on-chain integer amount of the output asset (before adjusting for decimals).
            decimals_out (int): The number of decimal places for the output asset.
            tplus_user (:class:`~tplus.models.types.UserPublicKey`): The public key of the user associated with the
              settlement request.
            chain (:class:`~tplus.models.types.ChainID`): The blockchain network identifier where the
              settlement will occur.
            settler (:class:`~tplus.models.types.UserPublicKey`): The settler tplus account. If not provided, uses the
              same account as ``tplus_user``.
            sub_account_index (int): The settler account index to pull funds from.

        Returns:
            InnerSettlementRequest: A normalized settlement request ready for processing.
        """
        return cls.model_validate(
            {
                "mode": mode,
                "asset_in": asset_in,
                "amount_in": to_inventory_decimals(amount_in, decimals_in, "up"),
                "asset_out": asset_out,
                "amount_out": to_inventory_decimals(amount_out, decimals_out, "down"),
                "tplus_user": tplus_user,
                "settler": settler or tplus_user,
                "chain_id": chain,
                "sub_account_index": sub_account_index,
            }
        )

    def signing_payload(self) -> str:
        base_data = self.model_dump(mode="json", exclude_none=True)

        user = base_data.pop("tplus_user")
        settler = base_data.pop("settler")
        chain_id = base_data.pop("chain_id", None)

        # NOTE: The order here matters!
        payload = {
            "tplus_user": user,
            "sub_account_index": base_data.pop("sub_account_index"),
            "settler": settler,
            **base_data,
            "chain_id": chain_id,
        }

        return (
            json.dumps(payload, separators=(",", ":"))
            .replace(" ", "")
            .replace("\n", "")
            .replace("\t", "")
        )


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
            if "settler" not in inner:
                inner["settler"] = signer.public_key

            inner = InnerSettlementRequest.model_validate(inner)

        signing_payload = inner.signing_payload()

        signature = str_to_vec(signer.sign(signing_payload).hex())
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

    signature: list[int] = []
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
    Batch settlement inner request.
    """

    tplus_user: UserPublicKey
    """
    The user whose signature will be validated.
    """

    sub_account_index: int
    """
    Subaccount to pull the settled funds from.
    """

    settler: UserPublicKey
    """
    The settler executing the settlement.
    """

    orders: list[BaseSettlement]
    """
    The settlement orders.
    """

    transactions: list[dict]
    """
    Transactions in the bundle (not including the push and pull transactions on the vault).
    """

    chain_id: ChainID
    """
    The chain settling on.
    """

    def signing_payload(self) -> str:
        return (
            self.model_dump_json(exclude_none=True)
            .replace(" ", "")
            .replace("\r", "")
            .replace("\n", "")
        )
