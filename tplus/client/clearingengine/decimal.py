from tplus.client.base import BaseClient
from tplus.model.asset_identifier import AssetIdentifier


class DecimalClient(BaseClient):
    """
    APIs related to decimals.
    """

    async def get_decimals(self, asset_id: list[str | AssetIdentifier], chains: list[int]) -> dict:
        """
        Get CE cached decimals for the given assets and chains.

        Args:
            asset_id (list[str | AssetIdentifier]): Asset identifiers.
            chains (list[int]): Chains identifiers.

        Returns:
            A mapping of asset Ids => chains => decimals.
        """
        assets = []
        for asset in asset_id:
            if not isinstance(asset, AssetIdentifier):
                asset = AssetIdentifier.model_validate(asset_id).model_dump()

            assets.append(asset)

        return await self._get("decimals", json_data={"assets": assets, "chains": chains})
