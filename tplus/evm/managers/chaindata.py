import asyncio
from collections.abc import Sequence
from typing import TYPE_CHECKING

from tplus.client.clearingengine import ClearingEngineClient
from tplus.evm.managers.evm import ChainConnectedManager
from tplus.model.types import ChainID

if TYPE_CHECKING:
    from tplus.model.asset_identifier import AssetIdentifier
    from tplus.utils.user import User


class ChainDataFetcher(ChainConnectedManager):
    """
    A manager for updating the clearing-engine with chain data.
    """

    def __init__(
        self,
        tplus_user: "User",
        clearing_engine: ClearingEngineClient | None = None,
        chain_id: ChainID | None = None,
    ):
        self.tplus_user = tplus_user
        self.ce: ClearingEngineClient = clearing_engine or ClearingEngineClient(
            self.tplus_user, "http://127.0.0.1:3032"
        )
        self.chain_id = chain_id or ChainID.evm(self.chain_manager.chain_id)

    async def prefetch_chaindata(
        self,
        vaults: bool = True,
        assets: bool = True,
        decimals: Sequence["AssetIdentifier"] | None = None,
        deposits: bool = True,
        settlements: bool = True,
    ):
        """
        Do any initial set up on a fresh CE, such as check for new vaults and deposits.
        """
        await self.ensure_vault_registered(check_for_new_vaults=vaults)

        if assets:
            await self.sync_assets()

        # Next, force the decimals to update. This isn't really needed but helps things run consistently from the go.
        if dec := decimals:
            await self.update_decimals(dec)

        # Ingest the deposits that you should have already made by running `ape run deposit`, else this won't
        # do anything for the CE, but you can always run `ape run ingest deposits` separately.
        if deposits:
            await self.sync_deposits()

        # Ingest past settlements or else the nonce and user balances will be wrong.
        if settlements:
            await self.sync_settlements()

    async def ensure_vault_registered(self, check_for_new_vaults: bool) -> None:
        if check_for_new_vaults:
            await self.sync_vaults()

            await asyncio.sleep(2)  # Give CE time to register vaults.

        for attempt in range(2):  # Try up to 2 times
            ce_vaults = await self.ce.vaults.get()
            if ce_vaults:
                return

            await asyncio.sleep(2)

        raise ValueError("Vault never registered.")

    async def sync_vaults(self):
        await self.ce.vaults.update()

    async def sync_assets(self):
        await self.ce.assets.update()

    async def sync_deposits(self):
        await self.ce.deposits.update(self.tplus_user.public_key, self.chain_id)

    async def sync_settlements(self):
        await self.ce.settlements.update(self.tplus_user.public_key, self.chain_id)

    async def update_decimals(self, assets: Sequence["AssetIdentifier"]):
        await self.ce.decimals.update(
            list(assets),
            [self.chain_id],
        )
