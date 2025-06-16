from tplus.client.base import BaseClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.settlement import BundleSettlementRequest, TxSettlementRequest


class ClearingEngineClient(BaseClient):
    async def get_decimals(self, asset_id: list[str | AssetIdentifier], chains: list[int]):
        assets = []

        for asset in asset_id:
            if not isinstance(asset, AssetIdentifier):
                asset = AssetIdentifier.model_validate(asset_id).model_dump()

            assets.append(asset)

        return await self._request(
            "GET", "decimals", json_data={"assets": assets, "chains": chains}
        )

    async def get_signatures(self, user: str):
        return await self._request("GET", f"settlement/signatures/{user}")

    async def get_assets(self):
        return await self._request("GET", "assets")

    async def update_assets(self, registry_chain_id: int):
        return await self._request(
            "POST", "assets/update", json_data={"registry_chain_id": registry_chain_id}
        )

    async def update_risk_parameters(self, registry_chain_id: int):
        return await self._request(
            "POST", "params/update", json_data={"registry_chain_id": registry_chain_id}
        )

    async def init_settlement(self, request: dict | TxSettlementRequest):
        if isinstance(request, dict):
            # Validate.
            request = TxSettlementRequest.model_validate(request)

        data = request.model_dump()
        return await self._request("POST", "settlement/init", json_data=data)

    async def init_bundle_settlement(self, request: dict | BundleSettlementRequest):
        if isinstance(request, dict):
            # Validate.
            request = BundleSettlementRequest.model_validate(request)

        json_data = request.model_dump(mode="json")
        return await self._request("POST", "settlement/init-bundle", json_data=json_data)
