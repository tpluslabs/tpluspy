from typing import Any

from pydantic import model_serializer, model_validator

from tplus.model.chain_address import ChainAddress, validate_chain_address


class AssetIdentifier(ChainAddress):
    """
    Represents an asset identifier, typically as a string (e.g., "SYMBOL@EXCHANGE" or a unique ID).
    It can be initialized with a user-friendly string like "0x...address@42161" (chain as integer ID),
    a pre-formatted string like "hex_address@hex_chain", an index string like "12345",
    or deserialized from the OMS dictionary format
    e.g., {"Index": 12345} or {"Address": {"address": [...], "chain": [...]}}.
    """

    root: str

    @model_validator(mode="before")
    @classmethod
    def _validate_input(cls, data: Any) -> Any:
        # Index.
        if isinstance(data, int) or isinstance(data, str) and data.isnumeric():
            return f"{data}"

        return validate_chain_address(data)

    def __str__(self) -> str:
        return str(self.root)

    @model_serializer
    def serialize_model(self) -> str:
        return self.root
