from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.asset_identifier import ChainAddress


class AssetRegistryClient(BaseClearingEngineClient):
    """
    Clearing engine APIs related to assets.
    """

    async def get_registry_address(self) -> ChainAddress:
        """
        Get the address of the registry the CE is pointed at.
        """
        return await self._get("registry")  # type: ignore

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

    async def set_registry_address(self, registry_address: ChainAddress):
        """
        Admin-only endpoint for setting the registry address. Used in testing environment.
        """
        payload = registry_address.model_dump()
        await self._post("admin/registry/update-address", json_data=payload)

    async def update_fee_account(self):
        """
        Request that the clearing engine update its fee account.
        """
        await self._post("fee-account/update")

    async def get_fee_account(self) -> str:
        """
        Get the fee account.
        """
        account = await self._get("fee-account")
        return f"{account}"
