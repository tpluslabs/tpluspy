from functools import cached_property
from typing import Any, TypeAlias

from eth_pydantic_types.hex.str import HexStr32
from pydantic import model_serializer, model_validator
from pydantic_core.core_schema import str_schema, with_info_before_validator_function

from tplus.model.chain_address import ChainAddress, validate_chain_address

AssetAddress: TypeAlias = ChainAddress


class Address32(HexStr32):
    """
    An unprefixed 32-byte hex string type.
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, value, handler=None):
        str_size = cls.size * 2
        return with_info_before_validator_function(
            cls.__eth_pydantic_validate__,
            str_schema(max_length=str_size, min_length=str_size),
        )

    @classmethod
    def __eth_pydantic_validate__(cls, value, info=None, **kwargs):
        return super().__eth_pydantic_validate__(value, info=info, prefixed=False, **kwargs)


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

    @cached_property
    def indexed(self):
        return "@" not in self.root

    @model_serializer
    def serialize_model(self) -> str:
        return self.root

    @property
    def evm_address(self) -> str:
        if self.indexed:
            raise ValueError("Indexed asset identifiers do not have an address.")

        return super().evm_address
