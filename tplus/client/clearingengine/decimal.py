from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.asset_identifier import AssetIdentifier


def _prep_request(
    asset_ids: list[str | AssetIdentifier] | str | AssetIdentifier, chains: list[int] | int
) -> dict:
    if not isinstance(asset_ids, list):
        asset_ids = [asset_ids]
    if not isinstance(chains, list):
        chains = [chains]

    assets = []
    for asset in asset_ids:
        if not isinstance(asset, AssetIdentifier):
            asset = AssetIdentifier.model_validate(asset)

        assets.append(asset.model_dump())

    return {"assets": assets, "chains": chains}


class DecimalClient(BaseClearingEngineClient):
    """
    APIs related to decimals.
    """

    async def get(self, asset_id: list[str | AssetIdentifier], chains: list[int]) -> dict:
        """
        Get CE cached decimals for the given assets and chains.

        Args:
            asset_id (list[str | AssetIdentifier]): Asset identifiers.
            chains (list[int]): Chains identifiers.

        Returns:
            A mapping of asset Ids => chains => decimals.
        """
        request = _prep_request(asset_id, chains)
        return await self._get("decimals", json_data=request)

    async def update(self, asset_id: list[str | AssetIdentifier], chains: list[int]):
        """
        Request that the CE update cache decimals for the given assets and chains.
        """
        request = _prep_request(asset_id, chains)
        await self._post("decimals/update", json_data=request)
