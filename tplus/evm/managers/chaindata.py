import asyncio
from collections.abc import Sequence
from typing import TYPE_CHECKING

from tplus.client.clearingengine import ClearingEngineClient
from tplus.client.oms.assetregistry import AssetRegistryClient
from tplus.evm.managers.evm import ChainConnectedManager
from tplus.model.types import ChainID

if TYPE_CHECKING:
    from tplus.model.asset_identifier import AssetAddress
    from tplus.utils.user import User


class ChainDataFetcher(ChainConnectedManager):
    """
    A manager for updating the clearing-engine with chain data.
    """

    def __init__(
        self,
        default_user: "User",
        clearing_engine: ClearingEngineClient | None = None,
        asset_registry: AssetRegistryClient | None = None,
        chain_id: ChainID | None = None,
    ):
        self.default_user = default_user
        self.ce: ClearingEngineClient = clearing_engine or ClearingEngineClient.from_local(
            self.default_user
        )
        self.asset_registry = asset_registry
        self.chain_id = chain_id or ChainID.evm(self.chain_manager.chain_id)

    async def prefetch_chaindata(
        self,
        vaults: bool = True,
        assets: bool = True,
        decimals: Sequence["AssetAddress"] | None = None,
    ):
        """
        Do any initial set up on a fresh CE, such as check for new vaults.
        """
        await self.ensure_vault_registered(check_for_new_vaults=vaults)

        if assets:
            await self.sync_assets()

        if dec := decimals:
            await self.update_decimals(dec)

    async def ensure_vault_registered(self, check_for_new_vaults: bool) -> None:
        if check_for_new_vaults:
            await self.sync_vaults()

            await asyncio.sleep(2)  # Give CE time to register vaults.

        if self.asset_registry is None:
            raise ValueError(
                "Asset registry client is required to check vault registration via OMS."
            )

        for attempt in range(2):  # Try up to 2 times
            oms_vaults = await self.asset_registry.get_vaults()
            if oms_vaults:
                return

            await asyncio.sleep(2)

        raise ValueError("Vault never registered.")

    async def sync_vaults(self):
        await self.ce.vaults.update()

    async def sync_assets(self):
        await self.ce.assets.update()

    async def update_decimals(self, assets: Sequence["AssetAddress"]):
        if self.asset_registry is None:
            raise ValueError(
                "Asset registry client is required to trigger decimals refresh via OMS."
            )
        await self.asset_registry.update_asset_decimals(list(assets))
