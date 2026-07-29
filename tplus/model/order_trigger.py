from typing import Any

from pydantic import BaseModel, model_serializer

from tplus.model.order_id import UserOrderId


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
    parent_order_id: UserOrderId | None
    trigger: TriggerAbove | TriggerBelow

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, Any] | str | None]:
        return {
            "parent_order_id": self.parent_order_id,
            "condition": self.trigger.serialize_model(),
        }
