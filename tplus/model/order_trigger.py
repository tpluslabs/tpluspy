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


class OrderTrigger(BaseModel):
    parent_order_id: str | None
    trigger: TriggerAbove | TriggerBelow

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, Any] | str]:
        if self.parent_order_id is not None:
            return {
                "parent_order_id": self.parent_order_id,
                "trigger": self.trigger.serialize_model(),
            }
        return {"trigger": self.trigger.serialize_model()}
