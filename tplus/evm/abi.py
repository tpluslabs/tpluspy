from typing import TYPE_CHECKING

from ape_tokens.testing import MockERC20
from ape_tokens.types import ERC20

if TYPE_CHECKING:
    from ethpm_types import ContractType


def get_erc20_type() -> "ContractType":
    """
    Get an ERC20 contract type.
    """
    return ERC20.model_copy()


def get_test_erc20_type() -> "ContractType":
    """
    Get an ERC20 contract type with a ``mint()`` method.
    """
    return MockERC20.contract_type.model_copy()
