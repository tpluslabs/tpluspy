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
        balance: dict,
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
                "balance": balance,
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

    async def set_asset_config(self, asset_index, chain_id: str, max_deposits: str, address: str, max_1hr_deposits: str):
        config = {"address": address,
                  "max_deposits": max_deposits,
                  "max_1hr_deposits": max_1hr_deposits
                  }

        await self._post(
                "admin/asset-config/modify",
                json_data={"asset_index": asset_index,
                           "chain_id": chain_id,
                           "config": config
                           }
        )



    async def set_risk_parameters(
            self,
            asset_id: AssetIdentifier,
            collateral_factor: int,
            liability_factor: int,
            max_collateral: str,
            max_total_open_interest_notional: str,
            max_open_interest: str,
            max_utilization: str,
            isolated_only: bool,
            initial_margin_clamps: list[int],
            initial_margin_factors: list[int],
            max_funding_rate: int,
            max_utilization_rate: int,
    ):
        risk_parameters = {
            "collateral_factor": collateral_factor,
            "liability_factor": liability_factor,
            "max_collateral": max_collateral,
            "max_total_open_interest_notional": max_total_open_interest_notional,
            "max_open_interest": max_open_interest,
            "max_utilization": max_utilization,
            "isolated_only": isolated_only,
            "initial_margin_clamps": initial_margin_clamps,
            "initial_margin_factors": initial_margin_factors,
            "max_funding_rate": max_funding_rate,
            "max_utilization_rate": max_utilization_rate,
          }
        await self._post(
            "admin/risk-parameters/modify",
            json_data={"asset_id": str(asset_id),
                       "risk_parameters": risk_parameters,
                       }
        )

    async def set_oracle_prices(self, asset_id: AssetIdentifier, asset_price:str, asset_price_decimals:int):
        prices= {
            str(asset_id): {"price": asset_price, "decimals":asset_price_decimals}
        }

        await self._post(
            "admin/oracle-prices/modify",
            json_data={"prices": prices}
        )

    async def set_last_trade(self, asset_id: AssetIdentifier, asset_last_price:str, asset_last_price_decimals:int):
        prices= {
            str(asset_id): {"price":asset_last_price, "decimals":asset_last_price_decimals}
        }

        await self._post(
            "admin/last-trade-price/modify",
            json_data={"prices": prices}
        )