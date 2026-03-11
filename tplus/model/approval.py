from eth_pydantic_types import HexBytes
from pydantic import BaseModel


class InnerSettlementApproval(BaseModel):
    nonce: int
    signature: HexBytes


class SettlementApproval(BaseModel):
    inner: InnerSettlementApproval
    expiry: int
