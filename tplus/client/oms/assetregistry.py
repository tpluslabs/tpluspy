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

    async def get_netting_parameters(self) -> list[dict]:
        """
        Get the asset-netting table OMS is pricing against
        (`GET /registry/netting-parameters`).

        Rows are `{asset, venue, venue_asset, cost, residual}` with `cost` and
        `residual` ppm-encoded. An empty list means the table is synced and no
        offsetting is configured; a 503 means OMS has not received one from the
        clearing engine yet, and raises.
        """
        response = await self._get("registry/netting-parameters", requires_auth=False)
        if not isinstance(response, list):
            raise TypeError(f"Expected list response for netting parameters, got: {type(response)}")
        return response

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

    async def get_vaults(self) -> list[ChainAddress]:
        """
        Get vault addresses (`GET /registry/vaults`).
        """
        response = await self._get("registry/vaults", requires_auth=False)
        if not isinstance(response, list):
            raise TypeError(f"Expected list response for registry vaults, got: {type(response)}")
        return [ChainAddress.model_validate(v) for v in response]
