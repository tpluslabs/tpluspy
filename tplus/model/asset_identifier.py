from functools import cached_property
from typing import Any

from pydantic import RootModel, model_serializer, model_validator


def _parse_asset_from_dict(data: dict) -> str:
    if "Address" in data:
        return _parse_chain_address_from_dict(data)

    # Backend sends an Index
    elif "Index" in data:
        return str(data["Index"])

    raise ValueError("Invalid dictionary for AssetIdentifier: must have 'Address' or 'Index' key")


def _parse_chain_address_from_dict(data: dict) -> str:
    if not (addr_data := data.get("Address")):
        raise ValueError("Invalid dictionary for ChainAddress: must have 'Address' key")

    # Backend sends a dict with byte arrays for address and chain
    if isinstance(addr_data, dict) and "address" in addr_data and "chain" in addr_data:
        addr_bytes = bytes(addr_data["address"])
        chain_bytes = bytes(addr_data["chain"])
        addr_hex = addr_bytes.hex()
        chain_hex = chain_bytes.hex()
        return f"{addr_hex}@{chain_hex}"

    # This case seems ambiguous, but we'll pass it through.
    elif isinstance(addr_data, str):
        return addr_data

    raise ValueError("Invalid Address")


def parse_chain_address(data: str) -> str:
    """
    Parse a chain-address str (e.g. AssetIdentifier or VaultAddress).
    """
    address, chain_part = data.split("@", 1)

    if address.startswith("0x"):
        address = address[2:]

    # Ensure address is 32 bytes (standard EVM uses 20, but we support multiple chains).
    address = bytes.fromhex(address).ljust(32, b"\x00").hex()

    try:
        chain_id = int(chain_part)
    except ValueError:
        # If not a decimal, assume it's already a hex string.
        # Return with address part normalized (no "0x" prefix).
        chain_hex = bytes.fromhex(chain_part).rjust(8, b"\x00").hex()

    else:
        num_bytes = ((chain_id.bit_length() + 7) // 8) or 1
        chain_hex = chain_id.to_bytes(num_bytes, "big").rjust(8, b"\x00").hex()

    return f"{address}@{chain_hex}"


class ChainAddress(RootModel[str]):
    """
    Identifies an address on a chain in format hex_address@hex_chain.
    """

    @model_validator(mode="before")
    @classmethod
    def _validate_input(cls, data: Any) -> Any:
        # Case 1: Input is a dictionary from the backend (e.g., from JSON deserialization)
        if isinstance(data, dict):
            return _parse_chain_address_from_dict(data)

        # Case 2: Input is a user-friendly string like "0x...address@chain_id"
        elif isinstance(data, str) and "@" in data:
            return parse_chain_address(data)

        # Also works for already validated AssetIdentifiers.
        return data

    def __str__(self) -> str:
        return str(self.root)

    @model_serializer
    def serialize_model(self) -> str:
        return self.root

    @cached_property
    def address(self) -> str:
        return self.root.split("@", 1)[0]

    @cached_property
    def evm_address(self) -> str:
        address = f"0x{self.address[:40]}"

        try:
            # NOTE: This is installed as a peer-dependency if using [evm] extras.
            from eth_utils import to_checksum_address

        except ImportError:
            return address  # Non-checksummed.

        return to_checksum_address(address)

    @cached_property
    def chain_id(self) -> int:
        return int(self.root.split("@")[-1], 16)


class AssetIdentifier(RootModel[str]):
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
        # Case 1: Input is a dictionary from the backend (e.g., from JSON deserialization)
        if isinstance(data, dict):
            return _parse_asset_from_dict(data)

        # Case 2: Input is a user-friendly string like "0x...address@chain_id"
        elif isinstance(data, str) and "@" in data:
            return parse_chain_address(data)

        elif isinstance(data, int):
            # int means index.
            return f"{data}"

        # Fallback for Index as string ("12345") or other valid inputs
        # Also works for already validated AssetIdentifiers.
        return data

    def __str__(self) -> str:
        return str(self.root)

    @model_serializer
    def serialize_model(self) -> str:
        return self.root
