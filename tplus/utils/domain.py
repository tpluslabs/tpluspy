from typing import TYPE_CHECKING

from eth_pydantic_types.hex.bytes import HexBytes32
from eth_utils import keccak

if TYPE_CHECKING:
    from tplus.model.chain_address import ChainAddress

# Pre-encoded schema version, 32 bytes
SCHEMA_VERSION = bytes([0] * 31 + [1])


def int_to_bytes32(value: int) -> HexBytes32:
    return HexBytes32.__eth_pydantic_validate__(value)


def get_dstack_domain(vault: "ChainAddress") -> HexBytes32:
    chain = vault.chain_id

    parts = [
        vault.address_bytes,
        int_to_bytes32(chain.routing_id),
        int_to_bytes32(chain.vm_id),
        SCHEMA_VERSION,
    ]

    concatenated = b"".join(parts)
    return HexBytes32(keccak(concatenated))
