import json
from typing import TYPE_CHECKING

from eth_pydantic_types.hex.int import HexInt
from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.types import ChainID, UserPublicKey
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


class InnerSettlementRequest(BaseSettlement):
    """
    Atomic settlement inner request.
    """

    tplus_user: UserPublicKey
    chain_id: ChainID

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

        return json.dumps(payload).replace(" ", "").replace("\r", "").replace("\n", "")


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
        cls, inner: InnerSettlementRequest | dict, signer: "User"
    ) -> "TxSettlementRequest":
        if isinstance(inner, dict):
            inner = InnerSettlementRequest.model_validate(inner)

        signature = str_to_vec(signer.sign(inner.signing_payload()).hex())
        return cls(inner=inner, signature=signature)

    def signing_payload(self) -> str:
        return self.inner.signing_payload()


class BundleSettlementRequest(BaseModel):
    """
    Bundle settlement request.
    """

    inner: "InnerBundleSettlementRequest"
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
        cls, inner: "InnerBundleSettlementRequest", signer: "User"
    ) -> "BundleSettlementRequest":
        signature = str_to_vec(signer.sign(inner.signing_payload()).hex())
        return cls(inner=inner, signature=signature)

    def signing_payload(self) -> str:
        return self.inner.signing_payload()


class InnerBundleSettlementRequest(BaseModel):
    """
    Bundle settlement inner request. Does not contain any additional fields.
    """

    settlements: list[BaseSettlement]
    """
    All settlement included in the transaction bundle.
    """

    bundle: "SimBundleRequest"
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

    def signing_payload(self) -> str:
        return (
            self.model_dump_json(exclude_none=True)
            .replace(" ", "")
            .replace("\r", "")
            .replace("\n", "")
        )


class SimBundleRequest(BaseModel):
    """
    Data for the light-client to validate the transaction bundle.
    """

    bundle: dict  # NOTE: Not using the model here so Ape isn't required.
    """
    Bundle data. Should match the model expected in RPC ``mev_SimBundle``.
    """

    bundle_id: int
    """
    A bundle identifier, should be unique for all settlement.
    """
