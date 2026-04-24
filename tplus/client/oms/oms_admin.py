from tplus.client.base import BaseClient
from tplus.model.asset_identifier import AssetIdentifier


class OmsAdminClient(BaseClient):
    async def set_settings(
        self,
        solvency_verifier: str,
        auto_reduce_enabled: bool,
    ):
        config = {
            "solvency_verifier": solvency_verifier,
            "auto_reduce_enabled": auto_reduce_enabled,
        }

        await self._post(
            "admin/settings/modify",
            json_data=config,
        )

    async def force_auto_reduce_now(
        self,
        user_id: str,
        sub_account: int,
        asset_id: int | AssetIdentifier | str,
    ):
        if isinstance(asset_id, AssetIdentifier):
            serialized_asset_id = str(asset_id)
        elif isinstance(asset_id, int):
            serialized_asset_id = str(asset_id)
        else:
            serialized_asset_id = asset_id

        await self._post(
            "admin/auto-reduce/force-run",
            json_data={
                "user_id": user_id,
                "sub_account": sub_account,
                "asset_id": serialized_asset_id,
            },
        )
