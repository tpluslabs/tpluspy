from typing import Any

from eth_utils import is_checksum_address, is_hex_address, to_normalized_address
from pydantic import BaseModel, field_validator, model_serializer, model_validator

from tplus.model.asset_identifier import AssetAddress


class SyncSettlementTerms(BaseModel):
    """
    Settlement terms committed by a sync taker: which token of the market's base asset moves
    on which chain (``hex_address@hex_chain``; a fungible asset such as BTC can be backed by
    several tokens), and the per-(user, sub-account) vault settlement nonce the CE approval
    must consume. The quote leg is always USD; the CE picks the USD token. Amounts and
    counterparty come from the fill itself.
    """

    base_token: AssetAddress
    nonce: int


class SyncGTC(BaseModel):
    """Good-til-cancel; the Rust ``SyncTimeInForce::GoodTilCancel`` unit variant, on the wire ``"GTC"``."""

    @model_validator(mode="before")
    @classmethod
    def _unwrap_data(cls, data: Any) -> Any:
        if data == "GTC" or data == {"GTC": None} or data == {}:
            return {}
        if isinstance(data, SyncGTC):
            return data
        raise ValueError(f"not a GTC sync time-in-force: {data!r}")

    @model_serializer
    def serialize_model(self) -> str:
        return "GTC"


class SyncGTD(BaseModel):
    """Good-til-date; the Rust ``SyncTimeInForce::GoodTilDate``, on the wire ``{"GTD": {"timestamp_ns": ...}}``."""

    timestamp_ns: int

    @model_validator(mode="before")
    @classmethod
    def _unwrap_data(cls, data: Any) -> Any:
        if isinstance(data, dict) and set(data) == {"GTD"}:
            return data["GTD"]
        if isinstance(data, SyncGTD) or (isinstance(data, dict) and set(data) == {"timestamp_ns"}):
            return data
        raise ValueError(f"not a GTD sync time-in-force: {data!r}")

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, int]]:
        return {"GTD": {"timestamp_ns": self.timestamp_ns}}


SyncTimeInForce = SyncGTC | SyncGTD


class SyncMakerOrderDetails(BaseModel):
    """
    A market maker's quote, resting in that maker's own sync book (``POST /sync_book/create``).
    """

    limit_price: int
    quantity: int
    time_in_force: SyncTimeInForce = SyncGTC()
    executor_address: str = "0x0000000000000000000000000000000000000000"
    """Lowercase ``0x`` hex: the form the Rust ``Address`` serializes to, hence the signed one."""

    @model_validator(mode="before")
    @classmethod
    def _unwrap_data(cls, data: Any) -> Any:
        if isinstance(data, dict) and "SyncMaker" in data and len(data) == 1:
            return data["SyncMaker"]
        return data

    @field_validator("executor_address", mode="before")
    @classmethod
    def _canonical_executor_address(cls, value: Any) -> str:
        # A mixed-case address must carry a valid EIP-55 checksum; the canonical form is
        # lowercase because that is what the server re-serializes before verifying.
        if not isinstance(value, str) or not is_hex_address(value):
            raise ValueError(f"invalid executor_address {value!r}: expected an EVM address")
        prefixed = value if value[:2].lower() == "0x" else f"0x{value}"
        letters = [c for c in prefixed[2:] if c.isalpha()]
        mixed_case = any(c.islower() for c in letters) and any(c.isupper() for c in letters)
        if mixed_case and not is_checksum_address(prefixed):
            raise ValueError(f"invalid executor_address {value!r}: bad EIP-55 checksum")
        return to_normalized_address(prefixed)

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, Any]]:
        return {
            "SyncMaker": {
                "limit_price": self.limit_price,
                "quantity": self.quantity,
                "time_in_force": self.time_in_force.model_dump(),
                "executor_address": self.executor_address,
            }
        }


class SyncTakerOrderDetails(BaseModel):
    """
    An immediate-or-cancel limit order routed across one sync book and the main book. The
    orderbook picks the sync book that would fill the most of the order, then walks that
    book and the main book together by price, the main book winning equal-price ties. The
    sync-book share fills as one leg that settles on chain with that market maker as
    settler; the main-book share fills as regular fills. Sync liquidity is not taken first:
    execution can run main, then sync, then main again.
    """

    limit_price: int
    quantity: int
    settlement: SyncSettlementTerms

    @model_validator(mode="before")
    @classmethod
    def _unwrap_data(cls, data: Any) -> Any:
        if isinstance(data, dict) and "SyncTaker" in data and len(data) == 1:
            return data["SyncTaker"]
        return data

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, Any]]:
        # Field order must match the Rust `OrderType::SyncTaker` variant: it is part of the
        # signed order payload.
        return {
            "SyncTaker": {
                "limit_price": self.limit_price,
                "quantity": self.quantity,
                "settlement": {
                    "base_token": str(self.settlement.base_token),
                    "nonce": self.settlement.nonce,
                },
            }
        }
