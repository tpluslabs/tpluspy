from functools import cached_property
from typing import Any

from pydantic import RootModel, model_serializer, model_validator

from tplus.model.types import ChainID


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
    if chain_part.startswith("0x"):
        chain_part = chain_part[2:]
    if len(chain_part) != 18:
        raise ValueError("ChainID must contain 1 byte routing ID and 8 bytes VM ID.")

    # Ensure address is 32 bytes (standard EVM uses 20, but we support multiple chains).
    address = bytes.fromhex(address).ljust(32, b"\x00").hex()

    return f"{address}@{chain_part}"


def validate_chain_address(chain_address: str) -> str:
    # Case 1: Already validated.
    if isinstance(chain_address, ChainAddress):
        # Already validated.
        return chain_address

    # Case 2: Input is a dictionary from the backend (e.g., from JSON deserialization)
    elif isinstance(chain_address, dict):
        return _parse_asset_from_dict(chain_address)

    # Case 3: Valid strings.
    elif isinstance(chain_address, str):
        # Case 3.1: User-friendly string like "0x...address@chain_id"
        if "@" in chain_address:
            return parse_chain_address(chain_address)

    raise ValueError("Invalid ChainAddress")


class ChainAddress(RootModel[str]):
    """
    Identifies an address on a chain in format hex_address@hex_chain.
    """

    @model_validator(mode="before")
    @classmethod
    def _validate_input(cls, data: Any) -> Any:
        return validate_chain_address(data)

    def __str__(self) -> str:
        return str(self.root)

    def __contains__(self, key: Any) -> bool:
        if isinstance(key, int):
            return key == self.chain_id

        elif isinstance(key, str) and key.startswith("0x"):
            key_str = key.lstrip("0x")
            if len(key_str) % 2 != 0:
                key_str = f"0{key_str}"

            key_bytes = bytes.fromhex(key_str)
            addr = self.evm_address if len(key_bytes) == 20 else self.address
            addr = addr.lstrip("0x")
            if len(addr) % 2 != 0:
                addr = f"0{addr}"

            return bytes.fromhex(addr) == key_bytes

        # Attemps from the other side before returning False.
        return NotImplemented

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
    def chain_id(self) -> ChainID:
        return ChainID(self.root.split("@")[-1])
