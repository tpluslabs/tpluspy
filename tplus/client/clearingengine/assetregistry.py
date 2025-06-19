from tplus.client.base import BaseClient


class AssetRegistryClient(BaseClient):
    """
    Clearing engine APIs related to assets.
    """

    async def get(self) -> dict:
        """
        Get all registered assets in the CE.

        Returns:
            dict: A mapping of stringified asset index (base 10) to chain ID to asset information.
        """
        return await self._get("assets")

    async def get_risk_parameters(self):
        """
        Get all registered risk parameters in the CE.

        Returns:
            dict: A mapping of asset identifiers to their respective risk parameters.
        """
        return await self._get("params")

    async def update(self, registry_chain_id: int):
        """
        Request that the clearing engine updates its registered assets for the given registry chain.

        Args:
            registry_chain_id (int): The chain ID of the T+ registry to use.
        """
        await self._post("assets/update", json_data={"registry_chain_id": registry_chain_id})

    async def update_risk_parameters(self, registry_chain_id: int):
        """
        Request that the clearing engine updates its registered risk parameters.

        Args:
            registry_chain_id (int): The chain ID of the T+ registry to use.
        """
        await self._post("params/update", json_data={"registry_chain_id": registry_chain_id})
