from typing import TYPE_CHECKING

from eip712.messages import EIP712Domain, EIP712Message
from eth_pydantic_types import abi

from tplus.model.types import ChainID

if TYPE_CHECKING:
    from ape.types.address import AddressType


def Domain(chain_id: int | ChainID, verifying_contract: "AddressType") -> EIP712Domain:
    if not isinstance(chain_id, int):
        chain_id = chain_id.vm_id

    return EIP712Domain(
        name="MyrtleWyckoff",
        version="1.0.0",
        chainId=chain_id,
        verifyingContract=verifying_contract,
    )


class Order(EIP712Message):
    tokenOut: abi.address
    amountOut: abi.uint256
    tokenIn: abi.address
    amountIn: abi.uint256
    user: abi.bytes32
    nonce: abi.uint256
    validUntil: abi.uint256
