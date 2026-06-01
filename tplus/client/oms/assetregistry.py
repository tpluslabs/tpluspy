from typing import Any, cast

from tplus.client.auth import AuthenticatedClient
from tplus.model.asset_identifier import AssetAddress
from tplus.model.chain_address import ChainAddress


class AssetRegistryClient(AuthenticatedClient):
    """
    Public OMS APIs for registry snapshots received from CE.
    """

    async def get_asset_config(self) -> dict:
        """
        Get the current asset config map (`GET /registry/assets`).
        """
        return await self._get("registry/assets", requires_auth=False)

    async def get_risk_parameters(self) -> dict:
        """
        Get the current risk parameter map (`GET /registry/risk-parameters`).
        """
        return await self._get("registry/risk-parameters", requires_auth=False)

    async def get_asset_decimals(self, assets: list[str | AssetAddress | ChainAddress]) -> dict:
        """
        Get cached decimals for the given assets (`POST /registry/decimals`).
        """
        payload_assets: list[dict] = []
        for asset in assets:
            if isinstance(asset, ChainAddress):
                payload_assets.append(asset.model_dump())
            else:
                payload_assets.append(AssetAddress.model_validate(asset).model_dump())

        return await self._post(
            "registry/decimals",
            json_data={"assets": payload_assets},
            requires_auth=False,
        )

    async def update_asset_decimals(self, assets: list[str | AssetAddress | ChainAddress]) -> None:
        """
        Trigger decimals refresh (`POST /registry/decimals/update`).
        Note: max asset count per request is 100
        """
        payload_assets: list[dict] = []
        for asset in assets:
            if isinstance(asset, ChainAddress):
                payload_assets.append(asset.model_dump())
            else:
                payload_assets.append(AssetAddress.model_validate(asset).model_dump())

        await self._post(
            "registry/decimals/update",
            json_data={"assets": payload_assets},
            requires_auth=True,
        )

    async def get_vaults(self) -> list[dict]:
        """
        Get vault addresses (`GET /registry/vaults`).
        """
        response = await self._get("registry/vaults", requires_auth=False)
        if not isinstance(response, list):
            raise TypeError(f"Expected list response for registry vaults, got: {type(response)}")
        return cast(list[dict[Any, Any]], response)
