from decimal import Decimal

from pydantic import BaseModel


class AccountSolvency(BaseModel):
    """Represents solvency of  a single user account"""

    """Example: {'above_mm_requirement': True, 'distance_from_liquidation': '400000.000000'}"""
    above_mm_requirement: bool
    distance_from_liquidation: Decimal


class UserSolvency(BaseModel):
    """Represents a single user solvency: collection of solvency info of all user accounts"""

    """ Example: {'accounts': {'1': {'above_mm_requirement': True, 'distance_from_liquidation': '400000.000000'}}}"""
    accounts: dict[int, AccountSolvency]


def parse_user_solvency(data: dict) -> UserSolvency:
    accounts: dict[int, AccountSolvency] = {}

    for account_id, account_data in data.get("accounts", {}).items():
        accounts[int(account_id)] = AccountSolvency(
            above_mm_requirement=account_data["above_mm_requirement"],
            distance_from_liquidation=Decimal(account_data["distance_from_liquidation"]),
        )

    return UserSolvency(accounts=accounts)
