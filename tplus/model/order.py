from dataclasses import dataclass
from typing import List, Union

from tplus.model.asset_identifier import IndexAsset
from tplus.model.limit_order import LimitOrderDetails
from tplus.model.market_order import MarketOrderDetails


@dataclass
class Order:
    signer: List[int]
    order_id: str
    base_asset: IndexAsset
    details: Union[LimitOrderDetails, MarketOrderDetails]
    side: str
    creation_timestamp_ns: int

    def to_dict(self):
        return {
            "signer": self.signer,
            "order_id": self.order_id,
            "base_asset": self.base_asset.to_dict(),
            "details": self.details.to_dict(),
            "side": self.side,
            "creation_timestamp_ns": self.creation_timestamp_ns
        }


@dataclass
class CreateOrderRequest:
    order: Order
    signature: List[int]

    def to_dict(self):
        return {
            "CreateOrderRequest": {
                "order": self.order.to_dict(),
                "signature": self.signature
            }
        }


