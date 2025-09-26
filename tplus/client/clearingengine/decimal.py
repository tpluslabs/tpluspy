from collections.abc import Sequence

from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.asset_identifier import AssetIdentifier


def _prep_request(
    asset_ids: Sequence[str | AssetIdentifier] | str | AssetIdentifier, chains: list[int] | int
) -> dict:
    asset_ids_seq = asset_ids if isinstance(asset_ids, Sequence) else [asset_ids]
    chains = chains if isinstance(chains, Sequence) else [chains]
    assets = []
    for asset in asset_ids_seq:
        if isinstance(asset, AssetIdentifier):
            # Already validated.
            assets.append(asset.model_dump())

        elif isinstance(asset, str) and asset.startswith("0x") and "@" not in asset:
            # Chain ID missing. Validate against all given chains.
            for chain in chains:
                asset = AssetIdentifier(f"{asset}@{chain}")
                assets.append(asset.model_dump())

        else:
            # Try to validate.
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
