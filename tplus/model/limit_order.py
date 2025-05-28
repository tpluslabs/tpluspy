from typing import Any

from pydantic import BaseModel, model_serializer, model_validator


class GTC(BaseModel):
    post_only: bool

    @model_validator(mode="before")
    @classmethod
    def _unwrap_data(cls, data: Any) -> Any:
        if isinstance(data, dict) and "GTC" in data and len(data) == 1:
            return data["GTC"]
        return data

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, bool]]:
        # Replicates the old {"GTC": {"post_only": ...}} structure
        return {"GTC": {"post_only": self.post_only}}


class GTD(BaseModel):
    post_only: bool
    timestamp_ns: int

    @model_validator(mode="before")
    @classmethod
    def _unwrap_data(cls, data: Any) -> Any:
        if isinstance(data, dict) and "GTD" in data and len(data) == 1:
            return data["GTD"]
        return data

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, bool | int]]:
        return {"GTD": {"post_only": self.post_only, "timestamp_ns": self.timestamp_ns}}


class IOC(BaseModel):
    fill_or_kill: bool

    @model_validator(mode="before")
    @classmethod
    def _unwrap_data(cls, data: Any) -> Any:
        if isinstance(data, dict) and "IOC" in data and len(data) == 1:
            return data["IOC"]
        return data

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, bool]]:
        return {"IOC": {"fill_or_kill": self.fill_or_kill}}


class LimitOrderDetails(BaseModel):
    limit_price: int
    quantity: int
    time_in_force: GTC | GTD | IOC
    book_quantity_decimals: int
    book_price_decimals: int

    @model_validator(mode="before")
    @classmethod
    def _unwrap_data(cls, data: Any) -> Any:
        if isinstance(data, dict) and "Limit" in data and len(data) == 1:
            return data["Limit"]
        return data

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, Any]]:
        # Replicates the old {"Limit": {...}} structure
        # Nested time_in_force (GTC) will use its own serializer automatically
        limit_data = {
            "limit_price": self.limit_price,
            "quantity": self.quantity,
            "time_in_force": self.time_in_force,  # Pydantic handles nested dump
            "book_quantity_decimals": self.book_quantity_decimals,
            "book_price_decimals": self.book_price_decimals,
        }
        return {"Limit": limit_data}
