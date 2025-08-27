from typing import Any

from pydantic import BaseModel, model_serializer


class TriggerAbove(BaseModel):
    price: int

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, Any]]:
        data = {
            "price": self.price,
        }
        return {"PriceAbove": data}


class TriggerBelow(BaseModel):
    price: int

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, Any]]:
        data = {
            "price": self.price,
        }
        return {"PriceBelow": data}
