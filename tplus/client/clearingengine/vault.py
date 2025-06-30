from tplus.client.base import BaseClient
from tplus.model.asset_identifier import AssetIdentifier


class VaultClient(BaseClient):
    """
    APIs related to vaults.
    """

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
