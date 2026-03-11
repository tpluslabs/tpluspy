"""
User margin info models for the T+ margin system.

This module provides models to represent detailed margin information for user accounts,
including:
- Account equity: Total portfolio value at mark prices (no haircuts)
- Available margin: IM surplus - how much margin is available to open new positions
- Utilized margin: Total margin consumed by existing positions
- Maintenance margin surplus: Distance from liquidation (MM surplus)
- Per-position breakdown with notional values

The margin system uses min(oracle, LTP) pricing to compute surpluses,
matching the solvency check conjunction over both price types.
"""

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel


class PositionSide(str, Enum):
    """Direction of a margin position."""

    LONG = "Long"
    SHORT = "Short"


class PositionMarginInfo(BaseModel):
    """
    Margin details for a single position.

    Attributes:
        asset_id: Asset identifier (e.g., "Index:1")
        side: Position direction (Long or Short)
        size: Position size as a decimal (converted from inventory decimals)
        notional_value: size * mark_price
    """

    asset_id: str
    side: PositionSide
    size: Decimal
    notional_value: Decimal


class AccountMarginInfo(BaseModel):
    """
    Margin breakdown for a single sub-account.

    Attributes:
        account_equity: Total account value at mark prices (no CF/LF haircuts).
            This reflects the total portfolio value using min(oracle, LTP) pricing.

        available_margin: IM surplus - margin available to open new positions.
            Computed with IM pricing and CF/LF haircuts applied. A positive value
            means the account can open more positions; negative means the account
            fails the IM solvency check.

        utilized_margin: Total margin consumed by existing positions.
            This is the adjusted liability value with LF and IM pricing applied.
            Zero when the account has no positions.

        maintenance_margin_surplus: MM surplus - distance from liquidation.
            How much equity can drop before liquidation begins. A positive value
            means the account is safely above liquidation threshold.

        account_leverage: total_notional / equity. None if equity is zero or negative.
            Represents how leveraged the account is relative to its equity.

        is_solvent: Whether the account passes the IM solvency check.
            True means available_margin >= 0.

        positions: Per-position breakdown (only present if include_positions=True).
            Contains size and notional value for each position.
    """

    account_equity: Decimal
    available_margin: Decimal
    utilized_margin: Decimal
    maintenance_margin_surplus: Decimal
    account_leverage: Decimal | None
    is_solvent: bool
    positions: list[PositionMarginInfo] | None = None


class UserMarginInfo(BaseModel):
    """
    Top-level margin info response containing per-account data.

    Attributes:
        accounts: Mapping from sub-account index (as int) to margin info.
            Keys are sub-account indices (e.g., 0 for spot, 1 for margin).
    """

    accounts: dict[int, AccountMarginInfo]


def parse_position_margin_info(data: dict) -> PositionMarginInfo:
    """Parse a single position margin info from API response."""
    return PositionMarginInfo(
        asset_id=data["asset_id"],
        side=PositionSide(data["side"]),
        size=Decimal(data["size"]),
        notional_value=Decimal(data["notional_value"]),
    )


def parse_account_margin_info(data: dict) -> AccountMarginInfo:
    """Parse a single account margin info from API response."""
    positions = None
    if data.get("positions") is not None:
        positions = [parse_position_margin_info(p) for p in data["positions"]]

    leverage = None
    if data.get("account_leverage") is not None:
        leverage = Decimal(data["account_leverage"])

    return AccountMarginInfo(
        account_equity=Decimal(data["account_equity"]),
        available_margin=Decimal(data["available_margin"]),
        utilized_margin=Decimal(data["utilized_margin"]),
        maintenance_margin_surplus=Decimal(data["maintenance_margin_surplus"]),
        account_leverage=leverage,
        is_solvent=data["is_solvent"],
        positions=positions,
    )


def parse_user_margin_info(data: dict) -> UserMarginInfo:
    """
    Parse the user margin info API response.

    Args:
        data: Raw API response dict with structure:
            {"accounts": {"0": {...}, "1": {...}}}

    Returns:
        UserMarginInfo with parsed account margin data.
    """
    accounts: dict[int, AccountMarginInfo] = {}

    for account_id, account_data in data.get("accounts", {}).items():
        accounts[int(account_id)] = parse_account_margin_info(account_data)

    return UserMarginInfo(accounts=accounts)
