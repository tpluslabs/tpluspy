import json
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, field_serializer

from tplus.model.asset_identifier import Address32, AssetAddress
from tplus.model.multisig import AdditionalSigner
from tplus.model.types import ChainID, UserPublicKey
from tplus.utils.decimals import to_inventory_decimals
from tplus.utils.user import to_user

if TYPE_CHECKING:
    from tplus.types import UserLike


class SettlementMode(str, Enum):
    MARGIN = "margin"
    SPOT = "spot"


class BaseSettlement(BaseModel):
    """
    The shared fields for all inner settlement requests.
    """

    mode: SettlementMode = SettlementMode.MARGIN
    asset_in: Address32
    amount_in: int
    asset_out: Address32
    amount_out: int

    @field_serializer("amount_in", "amount_out")
    def serialize_amounts(self, val):
        return str(val)


class InnerSettlementRequest(BaseSettlement):
    """
    Atomic settlement inner request.
    """

    tplus_user: UserPublicKey
    sub_account_index: int
    settler: UserPublicKey | None = None
    chain_id: ChainID
    nonce: int
    expires_at: int | None = None
    """
    Optional expiry timestamp (ns) after which the CE refuses the request.
    """
    max_fee: int | None = None
    """
    The most the settlement may reserve for the rebalancing fee of its outgoing leg, in canonical
    (1e18) units of ``asset_out``: ``None`` accepts the protocol-calculated reservation, ``0``
    only a fee-free approval. Signed from protocol version 3 on.
    """
    protocol_version: int = 3
    """
    Layout of the signed payload. Version 1 (clients predating the field) signed
    ``"mm_pubkey": null``; version 2 drops it and commits the version instead; version 3 signs
    ``max_fee`` too, ``null`` when unset.
    """

    @field_serializer("max_fee")
    def serialize_max_fee(self, val: int | None) -> str | None:
        return None if val is None else str(val)

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
        nonce: int,
        settler: UserPublicKey | None = None,
        mode: SettlementMode = SettlementMode.MARGIN,
        expires_at: int | None = None,
        max_fee: int | None = None,
    ) -> "InnerSettlementRequest":
        """
        Create a request using raw amounts, normalized to CE decimals. ``max_fee`` is in
        canonical (1e18) units of ``asset_out``, not raw ones.
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
                "nonce": nonce,
                "sub_account_index": sub_account_index,
                "expires_at": expires_at,
                "max_fee": max_fee,
            }
        )

    def signing_payload(self) -> str:
        base_data = self.model_dump(mode="json", exclude_none=True)

        user = base_data.pop("tplus_user")
        settler = base_data.pop("settler", None)
        chain_id = base_data.pop("chain_id", None)
        nonce = base_data.pop("nonce")
        expires_at = base_data.pop("expires_at", None)
        max_fee = base_data.pop("max_fee", None)
        base_data.pop("protocol_version")
        if max_fee is not None and self.protocol_version < 3:
            raise ValueError("max_fee is signed from protocol version 3 on")

        # NOTE: The order here matters — must match the Rust struct field order
        # in `InnerSettlementRequest`, which is what `serde_json::to_string`
        # emits on the CE side.
        payload = {
            "tplus_user": user,
            "sub_account_index": base_data.pop("sub_account_index"),
        }
        payload["settler"] = settler

        payload.update(base_data)
        payload["chain_id"] = chain_id
        payload["nonce"] = nonce
        payload["expires_at"] = expires_at
        if self.protocol_version >= 3:
            payload["max_fee"] = max_fee
        if self.protocol_version == 1:
            payload["mm_pubkey"] = None
        if self.protocol_version != 1:
            payload["protocol_version"] = self.protocol_version

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

    additional_signers: list[AdditionalSigner] = []
    """
    Multisig co-signatures, for accounts the master key alone cannot authorize.
    """

    @classmethod
    def create_signed(
        cls,
        inner: InnerSettlementRequest | dict,
        signer: "UserLike",
    ) -> "TxSettlementRequest":
        """
        Create and sign a settlement request.

        Args:
            inner (:class:`~tplus.model.settlement.InnerSettlementRequest`): The inner part of
              the request (signature fields).
            signer:
            signer (:class:`~tplus.utils.user.model.User`): The tplus user signing.
        """
        signer = to_user(signer)

        if isinstance(inner, dict):
            if "tplus_user" not in inner:
                inner["tplus_user"] = signer.public_key

            inner = InnerSettlementRequest.model_validate(inner)

        signing_payload = inner.signing_payload()

        signature, additional_signers = signer.signing_parts(signing_payload)
        return cls(inner=inner, signature=signature, additional_signers=additional_signers)

    def signing_payload(self) -> str:
        return self.inner.signing_payload()
