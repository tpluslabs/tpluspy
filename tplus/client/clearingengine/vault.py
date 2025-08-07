from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.asset_identifier import AssetIdentifier


class VaultClient(BaseClearingEngineClient):
    """
    APIs related to vaults.
    """

    async def update(self, registry_chain_id: int):
        """
        Request that the CE check the registry contract for new registered vaults.
        """
        request = {"registry_chain_id": registry_chain_id}
        await self._post("vaults/update", request)

    async def update_balance(self, asset_id: AssetIdentifier | str, chain_id: int):
        """
        Request that the CE check the deposit vault for new deposits for
        the given user.

        Args:
            asset_id (AssetIdentifier | str): The asset identifier.
            chain_id (int): The chain ID to check.
        """
        request = {"asset_id": asset_id, "chain_id": chain_id}
        await self._post("vault/balance/update", json_data=request)

    async def get_vaults(self) -> dict:
        """
        Get all registered vaults.
        """
        return await self._get("vaults")
