from typing import Any

from pydantic import RootModel, model_serializer, model_validator


class AssetIdentifier(RootModel[str]):
    """
    Represents an asset identifier, typically as a string (e.g., "SYMBOL@EXCHANGE" or a unique ID).
    This model serializes to the format expected by the OMS server,
    e.g., {"Index": 12345} or {"Address": {"address": [...], "chain": [...]}}.
    It can be initialized with a user-friendly string like "0x...address@chain_name",
    a pre-formatted string like "hex_address@hex_chain", an index string like "12345",
    or deserialized from the OMS dictionary format.
    """

    root: str

    @model_validator(mode="before")
    @classmethod
    def _validate_input(cls, data: Any) -> Any:
        # Case 1: Input is a dictionary from the backend (e.g., from JSON deserialization)
        if isinstance(data, dict):
            if "Address" in data:
                addr_data = data["Address"]
                # Backend sends a dict with byte arrays for address and chain
                if (
                    isinstance(addr_data, dict)
                    and "address" in addr_data
                    and "chain" in addr_data
                ):
                    addr_bytes = bytes(addr_data["address"])
                    chain_bytes = bytes(addr_data["chain"])
                    addr_hex = addr_bytes.hex()
                    chain_hex = chain_bytes.hex()
                    return f"{addr_hex}@{chain_hex}"
                # This case seems ambiguous, but we'll pass it through.
                elif isinstance(addr_data, str):
                    return addr_data
            # Backend sends an Index
            elif "Index" in data:
                return str(data["Index"])
            else:
                raise ValueError(
                    "Invalid dictionary for AssetIdentifier: must have 'Address' or 'Index' key"
                )

        # Fallback for Index as string ("12345") or other valid inputs
        return data

    def __str__(self) -> str:
        return str(self.root)

    @model_serializer
    def serialize_model(self) -> dict[str, Any]:
        """
        Serializes the AssetIdentifier to the format expected by the Rust OMS.
        - "12345" -> {"Index": 12345}
        - "addr_hex@chain_hex" -> {"Address": {"address": [bytes...], "chain": [bytes...]}}
        """
        if "@" in self.root:
            parts = self.root.split("@", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid Address format for AssetIdentifier: {self.root}")

            address_hex, chain_hex = parts

            try:
                address_bytes = bytes.fromhex(address_hex)
                chain_bytes = bytes.fromhex(chain_hex)
            except ValueError as e:
                raise ValueError(f"Invalid hex string in AssetIdentifier '{self.root}': {e}") from e

            if len(address_bytes) > 32:
                raise ValueError(
                    f"Address part of AssetIdentifier is too long ({len(address_bytes)} > 32): {self.root}"
                )
            if len(chain_bytes) > 8:
                raise ValueError(
                    f"Chain part of AssetIdentifier is too long ({len(chain_bytes)} > 8): {self.root}"
                )

            # Pad with null bytes to match Rust struct size (32 for address, 8 for chain)
            padded_address = address_bytes.ljust(32, b"\0")
            padded_chain = chain_bytes.ljust(8, b"\0")

            return {
                "Address": {
                    "address": list(padded_address),
                    "chain": list(padded_chain),
                }
            }
        else:
            try:
                return {"Index": int(self.root)}
            except ValueError:
                raise ValueError(
                    f"AssetIdentifier root '{self.root}' is not a valid integer string for an Index type "
                    f"and does not appear to be an Address type (missing '@')."
                )
