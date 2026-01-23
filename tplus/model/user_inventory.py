from typing import Literal

from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier


class Spot(BaseModel):
    """Represents a single spot account with multiple assets"""
    spot_account_balance: dict[str, int]

class Balance(BaseModel):
    """Represents either credits or liabilities for given asset"""
    credits: int
    liabilities: int

class MarginPosition(BaseModel):
    """Represents a single margin position: what is borrowed to buy what"""
    """should be base - not asset"""
    asset: Balance
    quote: Balance

class Margin(BaseModel):
    """Represents a single margin account: Collection of margin postions"""
    margins: dict[str, MarginPosition]

class UserAccount(BaseModel):
    """Represents a single user account: Combination of spot and margin accounts"""
    kind: Literal["cross_margin", "isolated_margin", "spot"]
    spot: Spot
    margin: Margin

class UserInventory(BaseModel):
    """Represents a single user inventory: collection of user accounts"""
    accounts: dict[int, UserAccount]
    is_mm: bool

def parse_user_inventory(data: dict) -> UserInventory:
    accounts: dict[int, UserAccount] = {}

    for account_id_str, account_data in data["accounts"].items():
        account_id = int(account_id_str)

        # ---- Spot parsing ----
        spot_balances = {
            asset_id: balance
            for asset_id, balance in account_data.get("spot", {}).items()
        }
        spot = Spot(spot_account_balance=spot_balances)

        # ---- Margin parsing ----
        margin_positions = {
            asset_id: MarginPosition(
                asset=Balance(**position["asset"]),
                quote=Balance(**position["quote"]),
            )
            for asset_id, position in account_data.get("margins", {}).items()
        }
        margin = Margin(margins=margin_positions)

        # ---- UserAccount ----
        accounts[account_id] = UserAccount(
            kind=account_data["kind"],
            spot=spot,
            margin=margin,
        )

        return UserInventory(
            accounts=accounts,
            is_mm=data["is_mm"],
        )