from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tplus.model.asset_identifier import Address32, EvmAddress


def to_evm_address(address: "Address32 | str") -> "EvmAddress":
    address = address.replace("0x", "")
    address = f"0x{str(address)[:40]}"

    try:
        from eth_utils import to_checksum_address
    except ImportError:
        return address  # type: ignore

    try:
        return to_checksum_address(address)
    except Exception as err:
        raise ValueError(f"Invalid address '{address}'") from err
