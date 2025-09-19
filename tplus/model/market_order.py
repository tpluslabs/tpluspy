from typing import Any

from pydantic import BaseModel, model_serializer, model_validator


class MarketBaseQuantity(BaseModel):
    quantity: int
    max_sellable_amount: int | None  # max_sellable_quote_quantity


class MarketQuoteQuantity(BaseModel):
    quantity: int
    max_sellable_quantity: int | None  # max_sellable_base_quantity


class MarketQuantity(BaseModel):
    base_asset: MarketBaseQuantity | None = None
    quote_asset: MarketQuoteQuantity | None = None

    @model_validator(mode="after")
    def check_quantities(self) -> "MarketQuantity":
        if self.base_asset is not None and self.quote_asset is not None:
            raise ValueError("Only one of 'base_asset' or 'quote_asset' can be provided.")
        if self.base_asset is None and self.quote_asset is None:
            raise ValueError("One of 'base_asset' or 'quote_asset' must be provided.")
        return self

    @model_serializer
    def serialize_model(self) -> dict[str, int]:
        if self.base_asset is not None:
            return {"BaseAsset": self.base_asset.model_dump()}
        if self.quote_asset is not None:
            return {"QuoteAsset": self.quote_asset.model_dump()}
        raise ValueError("Either base_asset or quote_asset must be set.")


class MarketOrderDetails(BaseModel):
    quantity: MarketQuantity
    fill_or_kill: bool

    @model_validator(mode="before")
    @classmethod
    def _unwrap_data(cls, data: Any) -> Any:
        if isinstance(data, dict) and "Market" in data and len(data) == 1:
            market_data = data["Market"]
            if "quantity" in market_data:
                if "BaseAsset" in market_data["quantity"]:
                    market_data["quantity"] = {"base_asset": market_data["quantity"]["BaseAsset"]}
                elif "QuoteAsset" in market_data["quantity"]:
                    market_data["quantity"] = {"quote_asset": market_data["quantity"]["QuoteAsset"]}
            return market_data
        return data

    @model_serializer
    def serialize_model(self) -> dict[str, dict[str, Any]]:
        market_data = {
            "quantity": self.quantity.serialize_model(),
            "fill_or_kill": self.fill_or_kill,
        }
        return {"Market": market_data}
