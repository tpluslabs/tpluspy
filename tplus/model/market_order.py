from typing import Any

from pydantic import BaseModel, model_serializer, model_validator


class MarketOrderDetails(BaseModel):
    quantity: int
    fill_or_kill: bool
    book_quantity_decimals: int

    @model_validator(mode="before")
    @classmethod
    def _unwrap_data(cls, data: Any) -> Any:
        if isinstance(data, dict) and "Market" in data and len(data) == 1:
            return data["Market"]
        return data

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, Any]]:
        # Replicates the old {"Market": {"quantity": {"BaseAsset" : ...}, ...}} structure
        market_data = {
            "quantity": {"BaseAsset": self.quantity},
            "fill_or_kill": self.fill_or_kill,
            "book_quantity_decimals": self.book_quantity_decimals,
        }
        return {"Market": market_data}
