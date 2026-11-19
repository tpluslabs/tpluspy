from typing import TYPE_CHECKING

from eth_pydantic_types import Address

if TYPE_CHECKING:
    from tplus.model.asset_identifier import Address32, EvmAddress


EVM_ADDRESS_HEX_LENGTH = 40


def to_evm_address(address: "Address32 | str") -> "EvmAddress":
    address_hex = str(address).removeprefix("0x")
    if len(address_hex) < EVM_ADDRESS_HEX_LENGTH:
        raise ValueError(f"'{address}' is not an EVM address: it is shorter than 20 bytes.")

    if address_hex[EVM_ADDRESS_HEX_LENGTH:].strip("0"):
        raise ValueError(f"'{address}' is not an EVM address: its bytes past the first 20 are set.")

    return Address.__eth_pydantic_validate__(address_hex[:EVM_ADDRESS_HEX_LENGTH])
