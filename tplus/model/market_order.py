from typing import Any

from pydantic import BaseModel, model_serializer


class MarketOrderDetails(BaseModel):
    quantity: int
    fill_or_kill: bool

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, Any]]:
        # Replicates the old {"Market": {"quantity": {"BaseAsset" : ...}, ...}} structure
        market_data = {
            "quantity": {"BaseAsset": self.quantity},
            "fill_or_kill": self.fill_or_kill
        }
        return {"Market": market_data}


