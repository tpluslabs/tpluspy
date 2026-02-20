from collections.abc import Sequence

from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.chain_address import ChainAddress
from tplus.model.types import ChainID


def _prep_request(
    asset_ids: Sequence[str | AssetIdentifier] | str | AssetIdentifier, chains: list[ChainID] | str
) -> dict:
    asset_ids_seq = (
        [asset_ids]
        if isinstance(asset_ids, str) or isinstance(asset_ids, AssetIdentifier)
        else asset_ids
    )

    # type ignore to avoid type-related bugs when using str instead of ChainID.
    chains = [chains] if isinstance(chains, str) else chains  # type: ignore

    assets = []
    for asset in asset_ids_seq:
        if isinstance(asset, ChainAddress):
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

    async def get(self, asset_id: list[str | AssetIdentifier], chains: list[ChainID]) -> dict:
        """
        Get CE cached decimals for the given assets and chains.

        Args:
            asset_id (list[str | AssetIdentifier]): Asset identifiers.
            chains (list[str]): Chains identifiers.

        Returns:
            A mapping of asset Ids => chains => decimals.
        """
        request = _prep_request(asset_id, chains)
        return await self._get("decimals", json_data=request)

    async def update(self, asset_id: list[str | AssetIdentifier], chains: list[ChainID]):
        """
        Request that the CE update cache decimals for the given assets and chains.
        """
        request = _prep_request(asset_id, chains)
        await self._post("decimals/update", json_data=request)
