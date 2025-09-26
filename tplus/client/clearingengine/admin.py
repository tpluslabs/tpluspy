from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.types import UserPublicKey


class AdminClient(BaseClearingEngineClient):
    async def get_verifying_key(self):
        """
        Get a clearing-engine's verifying key.

        Returns:
            str | None
        """
        return await self._get("admin/verifying-key")

    async def modify_user_inventory(
        self, user: "UserPublicKey", asset: "AssetIdentifier", balance: dict
    ):
        """
        Admin-only API for testing.
        """
        if not isinstance(user, UserPublicKey):
            user = UserPublicKey.__validate_user__(user)
        if not isinstance(asset, AssetIdentifier):
            asset = AssetIdentifier.model_validate(asset)

        asset = asset.model_dump()
        await self._post(
            "admin/inventory/modify", json_data={"user": user, "asset": asset, "balance": balance}
        )

    async def get_user_inventory(self, user: "UserPublicKey"):
        """
        Admin-only API for checking a user inventory.
        """
        if not isinstance(user, UserPublicKey):
            user = UserPublicKey.__validate_user__(user)

        return await self._get(f"admin/inventory/{user}")
