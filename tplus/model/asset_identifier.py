from typing import Any

from pydantic import RootModel, model_serializer, model_validator


class AssetIdentifier(RootModel[str]):
    """
    Represents an asset identifier, typically as a string (e.g., "SYMBOL@EXCHANGE" or a unique ID).
    This model serializes to the format expected by the OMS server,
    e.g., {"Index": 12345} or {"Address": "SYMBOL@EXCHANGE"}.
    It can be initialized with a string or deserialized from the OMS dictionary format.
    """
    root: str

    @model_validator(mode='before')
    @classmethod
    def _validate_input(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "Address" in data:
                return data["Address"]
            elif "Index" in data:
                return str(data["Index"])
            else:
                raise ValueError("Invalid dictionary for AssetIdentifier: must have 'Address' or 'Index' key")
        return data

    def __str__(self) -> str:
        return str(self.root)

    @model_serializer
    def serialize_model(self) -> dict[str, Any]:
        if '@' in self.root:
            return {"Address": self.root}
        else:
            try:
                return {"Index": int(self.root)}
            except ValueError:
                raise ValueError(
                    f"AssetIdentifier root '{self.root}' is not a valid integer string for an Index type "
                    f"and does not appear to be an Address type (missing '@')."
                )
