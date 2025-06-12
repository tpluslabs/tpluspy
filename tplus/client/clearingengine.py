from tplus.client.base import BaseClient


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
