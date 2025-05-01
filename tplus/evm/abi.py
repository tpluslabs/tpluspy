from typing import TYPE_CHECKING

from ape_tokens.types import ERC20
from ethpm_types.abi import ABIType, MethodABI

if TYPE_CHECKING:
    from ethpm_types import ContractType


# Useful for test tokens that implement mint().
MINT_METHOD = MethodABI(
    type="function",
    name="mint",
    stateMutability="nonpayable",
    inputs=[
        ABIType(name="to", type="address", components=None, internal_type="address"),
        ABIType(name="amount", type="uint256", components=None, internal_type="uint256"),
    ],
    outputs=[],
)


def get_erc20_type() -> "ContractType":
    """
    Get an ERC20 contract type.
    """
    return ERC20.model_copy()


def get_test_erc20_type() -> "ContractType":
    """
    Get an ERC20 contract type with a ``mint()`` method.
    """
    contract_type = ERC20.model_copy()
    contract_type.abi.append(MINT_METHOD)
    return contract_type
