from tplus.client.base import BaseClient
from tplus.model.asset_identifier import AssetIdentifier


class ClearingEngineClient(BaseClient):
    async def get_decimals(self):
        return await self._request("GET", "decimals")

    async def get_signatures(self, user: str):
        return await self._request("GET", f"settlement/signatures/{user}")

    async def get_assets(self):
        return await self._request("GET", "assets")

    async def update_assets(self, registry_chain_id: int):
        return await self._request(
            "POST", "assets/update", json_data={"registry_chain_id": registry_chain_id}
        )

    async def update_risk_parameters(self, registry_chain_id: int):
        return self._request("POST", "params/update", json={"registry_chain_id": registry_chain_id})

    async def init_settlement(
        self,
        user: str,
        calldata: str,
        asset_in: AssetIdentifier,
        amount_in: int,
        asset_out: AssetIdentifier,
        amount_out: int,
        chain_id: int,
        signature: str,
    ):
        inner = {
            "tplus_user": user,
            "calldata": calldata,
            "asset_in": asset_in,
            "amount_in": amount_in,
            "asset_out": asset_out,
            "amount_out": amount_out,
            "chain_id": chain_id,
        }
        return await self._request(
            "POST", "settlement/init", json_data={"inner": inner, "signature": signature}
        )
