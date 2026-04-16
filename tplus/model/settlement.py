import json
from enum import Enum
from typing import TYPE_CHECKING

from eth_pydantic_types.hex.int import HexInt
from pydantic import BaseModel, field_serializer

from tplus.model.asset_identifier import Address32, AssetAddress
from tplus.model.types import ChainID, UserPublicKey
from tplus.utils.decimals import to_inventory_decimals
from tplus.utils.hex import str_to_vec

if TYPE_CHECKING:
    from tplus.utils.user import User


class SettlementMode(str, Enum):
    MARGIN = "margin"
    SPOT = "spot"


class BaseSettlement(BaseModel):
    """
    The shared fields for all inner settlement requests.
    """

    mode: SettlementMode = SettlementMode.MARGIN
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
    settler: UserPublicKey | None = None
    chain_id: ChainID
    expires_at: int | None = None
    """
    Optional expiry timestamp (ns). Required when ``mm_pubkey`` is set — the CE
    rejects delegated settlements without it to bound the replay window.
    """

    mm_pubkey: UserPublicKey | None = None
    """
    For delegated settlements: the market maker whose maker-order attachment is
    expected alongside this request. Committing ``mm_pubkey`` into the signed
    payload prevents a different MM from redirecting the settlement to their
    own settler. Must be ``None`` for non-delegated flows.
    """

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
        mode: SettlementMode = SettlementMode.MARGIN,
        expires_at: int | None = None,
    ) -> "InnerSettlementRequest":
        """
        Create a non-delegated request using raw amounts, normalized to CE decimals.
        ``mm_pubkey`` is always ``None`` here; use
        :meth:`from_raw_delegated` for delegated settlements.
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
                "expires_at": expires_at,
            }
        )

    @classmethod
    def from_raw_delegated(
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
        mm_pubkey: UserPublicKey,
        expires_at: int,
        mode: SettlementMode = SettlementMode.MARGIN,
    ) -> "InnerSettlementRequest":
        """
        Create a delegated settlement request bound to a specific MM.

        Both ``mm_pubkey`` and ``expires_at`` are required and committed into
        the signed payload; the CE rejects delegated settlements missing
        either. ``settler`` is always ``None`` — the CE derives the executor
        from the attached maker order.
        """
        return cls.model_validate(
            {
                "mode": mode,
                "asset_in": asset_in,
                "amount_in": to_inventory_decimals(amount_in, decimals_in, "up"),
                "asset_out": asset_out,
                "amount_out": to_inventory_decimals(amount_out, decimals_out, "down"),
                "tplus_user": tplus_user,
                "settler": None,
                "chain_id": chain,
                "sub_account_index": sub_account_index,
                "expires_at": expires_at,
                "mm_pubkey": mm_pubkey,
            }
        )

    def signing_payload(self) -> str:
        base_data = self.model_dump(mode="json", exclude_none=True)

        user = base_data.pop("tplus_user")
        settler = base_data.pop("settler", None)
        chain_id = base_data.pop("chain_id", None)
        expires_at = base_data.pop("expires_at", None)
        mm_pubkey = base_data.pop("mm_pubkey", None)

        # NOTE: The order here matters — must match the Rust struct field order
        # in `InnerSettlementRequest`, which is what `serde_json::to_string`
        # emits on the CE side.
        payload = {
            "tplus_user": user,
            "sub_account_index": base_data.pop("sub_account_index"),
        }
        if settler is not None:
            payload["settler"] = settler

        payload.update(base_data)
        payload["chain_id"] = chain_id
        if expires_at is not None:
            payload["expires_at"] = expires_at
        if mm_pubkey is not None:
            payload["mm_pubkey"] = mm_pubkey

        return (
            json.dumps(payload, separators=(",", ":"))
            .replace(" ", "")
            .replace("\n", "")
            .replace("\t", "")
        )


class InnerMakerOrderAttachment(BaseModel):
    """
    The signed inner part of a maker order attachment for delegated settlement.
    """

    mm_pubkey: UserPublicKey
    """The market maker's public key."""

    settler: UserPublicKey
    """The settler/executor designated by the MM."""

    expires_at: int
    """Expiry timestamp in nanoseconds."""


class MakerOrderAttachment(BaseModel):
    """
    A maker order attached to a delegated settlement request.
    """

    inner: InnerMakerOrderAttachment
    """The signed inner part."""

    signature: list[int]
    """MM's signature over ``inner``."""


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

    maker_order: MakerOrderAttachment | None = None
    """
    Optional maker order for delegated settlement.
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

        signing_payload = inner.signing_payload()

        signature = str_to_vec(signer.sign(signing_payload).hex())
        return cls(inner=inner, signature=signature)

    @classmethod
    def create_signed_delegated(
        cls,
        inner: InnerSettlementRequest | dict,
        signer: "User",
        maker_order: MakerOrderAttachment,
    ) -> "TxSettlementRequest":
        """
        Create and sign a delegated settlement request, cross-checking that
        ``inner.mm_pubkey`` matches the attached maker order's MM. The CE
        enforces this binding server-side; checking locally surfaces the
        mismatch earlier with a clearer error.
        """
        if isinstance(inner, dict):
            if "tplus_user" not in inner:
                inner["tplus_user"] = signer.public_key
            inner = InnerSettlementRequest.model_validate(inner)

        if inner.mm_pubkey is None:
            raise ValueError(
                "Delegated settlement requires inner.mm_pubkey to be set "
                "(use InnerSettlementRequest.from_raw_delegated)."
            )
        if inner.expires_at is None:
            raise ValueError(
                "Delegated settlement requires inner.expires_at to bound the replay window."
            )
        if inner.mm_pubkey != maker_order.inner.mm_pubkey:
            raise ValueError(
                "inner.mm_pubkey does not match maker_order.inner.mm_pubkey; "
                "the CE will reject this as MmPubkeyMismatch."
            )

        signature = str_to_vec(signer.sign(inner.signing_payload()).hex())
        return cls(inner=inner, signature=signature, maker_order=maker_order)

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
