from decimal import Decimal

from pydantic import BaseModel, Field


class Spot(BaseModel):
    """Represents a single spot account with multiple assets"""

    spot_account_balance: dict[str, Decimal]


class MarginPositionSide(BaseModel):
    """Represents either credits or liabilities for given asset"""

    credits: Decimal
    liabilities: Decimal


class MarginPosition(BaseModel):
    """Represents a single margin position: what is borrowed to buy what"""

    base: MarginPositionSide
    quote: MarginPositionSide


class Margin(BaseModel):
    """Represents a single margin account: Collection of margin postions"""

    margin_positions: dict[str, MarginPosition]


class UserAccount(BaseModel):
    """Represents a single user account: Combination of spot and margin accounts"""

    kind: str = Field(pattern=r"^(funding|cross_margin|isolated:[0-9]+)$")
    spot_token_balances: dict[str, Decimal | None]
    token_liabilities: dict[str, Decimal | None] | None = None
    spot_canonical_balances: Spot
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
            for asset_id, balance in account_data.get("spot_canonical_balances", {}).items()
        }
        spot = Spot(spot_account_balance=spot_balances)

        # ---- Margin parsing ----
        margin_positions = {
            asset_id: MarginPosition(
                base=MarginPositionSide(**position["base"]),
                quote=MarginPositionSide(**position["quote"]),
            )
            for asset_id, position in account_data.get("margin_positions", {}).items()
        }
        margin = Margin(margin_positions=margin_positions)

        # ---- UserAccount ----
        accounts[account_id] = UserAccount(
            kind=account_data["kind"],
            spot_token_balances=account_data["spot_token_balances"],
            token_liabilities=account_data.get("token_liabilities"),
            spot_canonical_balances=spot,
            margin=margin,
        )

    return UserInventory(
        accounts=accounts,
        is_mm=data["is_mm"],
    )
