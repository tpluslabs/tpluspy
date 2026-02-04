from pydantic import BaseModel


class AccountSolvency(BaseModel):
    """Represents solvency of  a single user account"""

    """Example: {'is_solvent': True, 'distance_from_liquidation': '400000.000000'}"""
    is_solvent: bool
    distance_from_liquidation: int


class UserSolvency(BaseModel):
    """Represents a single user solvency: collection of solvency info of all user accounts"""

    """ Example: {'accounts': {'1': {'is_solvent': True, 'distance_from_liquidation': '400000.000000'}}}"""
    accounts: dict[int, AccountSolvency]


def parse_user_solvency(data: dict) -> UserSolvency:
    accounts: dict[int, AccountSolvency] = {}

    for account_id, account_data in data.get("accounts", {}).items():
        accounts[int(account_id)] = AccountSolvency(
            is_solvent=account_data["is_solvent"],
            distance_from_liquidation=int(float(account_data["distance_from_liquidation"])),
        )

    return UserSolvency(accounts=accounts)
