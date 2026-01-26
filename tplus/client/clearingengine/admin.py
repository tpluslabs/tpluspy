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
        self,
        user: "UserPublicKey",
        asset: "AssetIdentifier",
        base_balance: dict,
        quote_balance: dict,
        spot_balance: int,
        sub_account_index: int = 1,
    ):
        """
        Admin-only API for testing.

        Args:
            user: The user's public key
            asset: The asset identifier
            balance: Dict with "credits" and "liabilities" keys
            sub_account_index: The sub-account index (0=main, 1=margin). Defaults to 1 (margin).
        """
        if not isinstance(user, UserPublicKey):
            user = UserPublicKey.__validate_user__(user)
        if not isinstance(asset, AssetIdentifier):
            asset = AssetIdentifier.model_validate(asset)

        asset = asset.model_dump()

        await self._post(
            "admin/inventory/modify",
            json_data={
                "user": user,
                "asset": asset,
                "balance": base_balance,
                "quote_balance": quote_balance,
                "spot": spot_balance,
                "sub_account_index": sub_account_index,
            },
        )

    async def get_user_inventory(self, user: "UserPublicKey"):
        """
        Admin-only API for checking a user inventory.
        """
        if not isinstance(user, UserPublicKey):
            user = UserPublicKey.__validate_user__(user)

        return await self._get(f"admin/inventory/{user}")
