from typing import TYPE_CHECKING

from tplus.evm.contracts import Registry
from tplus.evm.managers.evm import ChainConnectedManager
from tplus.model.types import ChainID
from tplus.utils.timeout import wait_for_condition

if TYPE_CHECKING:
    from ape.api.accounts import AccountAPI
    from ape.types.address import AddressType
    from eth_pydantic_types.hex.bytes import HexBytes32

    from tplus.client.clearingengine import ClearingEngineClient


class RegistryOwner(ChainConnectedManager):
    """
    For registry (`Registry.sol`) operations using the owner of the contract.
    """

    def __init__(
        self,
        owner: "AccountAPI",
        registry: Registry | None = None,
        chain_id: ChainID | None = None,
        clearing_engine: "ClearingEngineClient | None" = None,
    ):
        self.owner = owner
        self.chain_id = chain_id or ChainID.evm(self.chain_manager.chain_id)

        if registry is None:
            self.registry = Registry(chain_id=self.chain_id)
        else:
            self.registry = registry

        self.ce = clearing_engine

    async def set_asset(
        self,
        index: int,
        asset_address: "HexBytes32 | AddressType",
        chain_id: ChainID,
        max_deposit: int,
        max_1hr_deposits: int,
        min_weight: int,
        wait: bool = True,
        **tx_kwargs,
    ) -> None:
        if "sender" not in tx_kwargs:
            tx_kwargs["sender"] = self.owner

        self.registry.set_asset(
            index,
            asset_address,
            chain_id,
            max_deposit,
            max_1hr_deposits,
            min_weight,
            **tx_kwargs,
        )

        if wait:
            if not (ce := self.ce):
                raise ValueError("Must have clearing_engine to wait for asset registration.")

            await wait_for_condition(
                update_fn=lambda: ce.assets.update(),
                get_fn=lambda: ce.assets.get(),
                # cond: checks if the vault address is part any of the ChainAddress returned.
                check_fn=lambda assets: f"{index}" in assets,
                timeout=10,
                interval=1,
                error_msg=f"Asset registration failed (asset={index}).",
            )
