from tplus.client.clearingengine.base import BaseClearingEngineClient


class AssetRegistryClient(BaseClearingEngineClient):
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

    async def update(self):
        """
        Request that the clearing engine updates its registered assets for the given registry chain.
        """
        await self._post("assets/update")

    async def update_risk_parameters(self):
        """
        Request that the clearing engine updates its registered risk parameters.
        """
        await self._post("params/update")
