"""
Models for POST /account/simulate/{user_id} margin simulation responses.
"""

from decimal import Decimal

from pydantic import BaseModel

from tplus.model.user_margin import PositionSide


class SimulatedPositionMarginInfo(BaseModel):
    """Per-position breakdown after a simulated trade."""

    asset_id: str
    side: PositionSide
    size: Decimal
    notional_value: Decimal
    margin: Decimal


class UserSimulatedMargin(BaseModel):
    """Projected margin state after applying a hypothetical trade."""

    account_equity: Decimal
    available_margin: Decimal
    mm_surplus: Decimal
    account_leverage: Decimal | None
    utilized_margin: Decimal
    margin_required: Decimal
    margin_impact: Decimal
    is_solvent: bool
    trade_accepted: bool
    liquidation_price: Decimal | None = None
    positions: list[SimulatedPositionMarginInfo]


def parse_simulated_position_margin_info(data: dict) -> SimulatedPositionMarginInfo:
    return SimulatedPositionMarginInfo(
        asset_id=data["asset_id"],
        side=PositionSide(data["side"]),
        size=Decimal(data["size"]),
        notional_value=Decimal(data["notional_value"]),
        margin=Decimal(data["margin"]),
    )


def parse_user_simulated_margin(data: dict) -> UserSimulatedMargin:
    leverage = None
    if data.get("account_leverage") is not None:
        leverage = Decimal(data["account_leverage"])

    liquidation_price = None
    if data.get("liquidation_price") is not None:
        liquidation_price = Decimal(data["liquidation_price"])

    positions = [
        parse_simulated_position_margin_info(position) for position in data.get("positions", [])
    ]

    return UserSimulatedMargin(
        account_equity=Decimal(data["account_equity"]),
        available_margin=Decimal(data["available_margin"]),
        mm_surplus=Decimal(data["mm_surplus"]),
        account_leverage=leverage,
        utilized_margin=Decimal(data["utilized_margin"]),
        margin_required=Decimal(data["margin_required"]),
        margin_impact=Decimal(data["margin_impact"]),
        is_solvent=data["is_solvent"],
        trade_accepted=data["trade_accepted"],
        liquidation_price=liquidation_price,
        positions=positions,
    )
