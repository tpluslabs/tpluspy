from collections.abc import Sequence

from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.asset_identifier import AssetAddress
from tplus.model.chain_address import ChainAddress


def _prep_request(asset_ids: Sequence[str | AssetAddress] | str | AssetAddress) -> dict:
    asset_ids_seq = (
        [asset_ids]
        if isinstance(asset_ids, str) or isinstance(asset_ids, AssetAddress)
        else asset_ids
    )

    assets = []
    for asset in asset_ids_seq:
        if isinstance(asset, ChainAddress):
            # Already validated.
            assets.append(asset.model_dump())

        else:
            # Try to validate.
            asset = AssetAddress.model_validate(asset)
            assets.append(asset.model_dump())

    return {"assets": assets}


class DecimalClient(BaseClearingEngineClient):
    """
    APIs related to decimals.
    """

    async def get(self, address: list[str | AssetAddress]) -> dict:
        """
        Get CE cached decimals for the given assets.

        Args:
            address (list[str | AssetAddress]): Asset addresses.

        Returns:
            A mapping of asset address => decimals.
        """
        request = _prep_request(address)
        return await self._get("decimals", json_data=request)

    async def update(self, address: list[str | AssetAddress]):
        """
        Request that the CE update cached decimals for the given assets.
        """
        request = _prep_request(address)
        await self._post("decimals/update", json_data=request)
