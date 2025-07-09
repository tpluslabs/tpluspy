import json
from typing import TYPE_CHECKING

from eth_pydantic_types.hex.int import HexInt
from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.types import ChainID, UserPublicKey
from tplus.utils.hex import str_to_vec

if TYPE_CHECKING:
    from tplus.utils.user import User


class TxSettlementRequest(BaseModel):
    """
    Atomic settlement request.
    """

    inner: "InnerSettlementRequest"
    """
    The inner part of the request (signature fields).
    """

    signature: list[int]
    """
    The settler's signature from signing the necessary data (mostly from ``.inner``).
    """

    @classmethod
    def create_signed(
        cls, inner: "InnerSettlementRequest", signer: "User"
    ) -> "TxSettlementRequest":
        signature = str_to_vec(signer.sign(inner.signing_payload()).hex())
        return cls(inner=inner, signature=signature)

    def signing_payload(self) -> str:
        return self.inner.signing_payload()


class BundleSettlementRequest(BaseModel):
    """
    Bundle settlement request.
    """

    inner: list["InnerBundleSettlementRequest"]
    """
    The inner part of the request (signature fields).
    Allows multiple settlements, unlike ``TxSettlementRequest``.
    """

    bundle: "SimBundleRequest"
    """
    The MEV EVM standard bundle that fulfills the settlement (requires verification
    via mev_simBundle RPC).
    """

    signature: list[int]
    """
    The settler's signature from signing the necessary data (mostly from ``.inner``).
    """

    user: UserPublicKey
    """
    The settler.
    """

    chain_id: int
    """
    The chain ID of the deposit vault settling on.
    """


class BaseInnerSettlementRequest(BaseModel):
    """
    The shared fields for all inner settlement requests.
    """

    asset_in: AssetIdentifier
    amount_in: HexInt
    asset_out: AssetIdentifier
    amount_out: HexInt


class InnerSettlementRequest(BaseInnerSettlementRequest):
    """
    Atomic settlement inner request. Additionally, contains calldata for an on-chain
    settlement callback.
    """

    calldata: list[HexInt]
    chain_id: ChainID

    def signing_payload(self, settler: UserPublicKey) -> str:
        base_data = self.model_dump(mode="json", exclude_none=True)
        calldata = base_data.pop("calldata", [])

        # NOTE: The order here matters!
        payload = {
            "tplus_user": str_to_vec(settler),
            "calldata": calldata,
            **base_data,
        }

        return json.dumps(payload).replace(" ", "").replace("\r", "").replace("\n", "")


class InnerBundleSettlementRequest(BaseInnerSettlementRequest):
    """
    Bundle settlement inner request. Does not contain any additional fields.
    """


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
