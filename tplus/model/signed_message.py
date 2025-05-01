import json
from dataclasses import dataclass, asdict

from tplus.model.asset_identifier import IndexAsset
from tplus.model.order import CreateOrderRequest


@dataclass
class ObRequest:
    order_id: str
    base_asset: IndexAsset
    ob_request_payload: CreateOrderRequest

    def to_dict(self):
        return {
            "order_id": self.order_id,
            "base_asset": self.base_asset.to_dict(),
            "ob_request_payload": self.ob_request_payload.to_dict()
        }

@dataclass
class SignedMessage:
    payload: ObRequest
    user_id: str
    post_sign_timestamp: int

    def to_dict(self):
        return {
            "payload": self.payload.to_dict(),
            "user_id": self.user_id,
            "post_sign_timestamp": self.post_sign_timestamp
        }

