from functools import cached_property
from typing import TYPE_CHECKING

from ape_tokens.testing import MockERC20

from tplus.model.asset_identifier import AssetAddress, AssetIdentifier
from tplus.model.types import ChainID
from tplus.utils.amount import Amount

if TYPE_CHECKING:
    from ape.types.address import AddressType

    from tplus.model.chain_address import Address32


class Token:
    def __init__(self, contract: MockERC20, chain_id: ChainID, asset_index: int | None = None):
        self.contract = contract
        self._chain_id = chain_id
        self._asset_index = asset_index

    def get_amount(self, amount: int) -> Amount:
        return Amount(amount=amount, decimals=self.contract.decimals())

    @property
    def address(self) -> "AddressType":
        return self.contract.address

    @cached_property
    def asset_address(self) -> AssetAddress:
        """The on-chain address (always includes chain), for APIs that need it."""
        return AssetAddress.from_evm_address(self.address, self._chain_id)

    @property
    def tplus_address(self) -> "Address32":
        return self.asset_address.address

    @cached_property
    def asset_identifier(self) -> AssetIdentifier:
        if self._asset_index is not None:
            return AssetIdentifier(self._asset_index)

        return AssetIdentifier.from_evm_address(self.address, self._chain_id)
