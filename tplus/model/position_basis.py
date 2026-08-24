from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier

PositionBasisDomain = Literal["spot", "margin"]
PositionBasisSide = Literal["long", "short"]


class PositionBasisResponse(BaseModel):
    sub_account: int
    asset_id: AssetIdentifier
    domain: PositionBasisDomain
    side: PositionBasisSide | None = None
    quantity: Decimal
    cost: Decimal
    entry_price: Decimal | None = None
    avg_acquisition_price: Decimal | None = None
    mark_price: Decimal | None = None
    unrealized_pnl: Decimal | None = None


def parse_position_basis(data: list[dict]) -> list[PositionBasisResponse]:
    return [PositionBasisResponse.model_validate(item) for item in data]
