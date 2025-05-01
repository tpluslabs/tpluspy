from typing import Any

from pydantic import BaseModel, model_serializer


class GTC(BaseModel):
    post_only: bool

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, bool]]:
        # Replicates the old {"GTC": {"post_only": ...}} structure
        return {"GTC": {"post_only": self.post_only}}


class LimitOrderDetails(BaseModel):
    limit_price: int
    quantity: int
    time_in_force: GTC

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, Any]]:
        # Replicates the old {"Limit": {...}} structure
        # Nested time_in_force (GTC) will use its own serializer automatically
        limit_data = {
            "limit_price": self.limit_price,
            "quantity": self.quantity,
            "time_in_force": self.time_in_force # Pydantic handles nested dump
        }
        return {"Limit": limit_data}

