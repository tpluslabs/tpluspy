from pydantic import BaseModel

from tplus.utils.decimals import to_inventory_decimals


class Amount(BaseModel):
    """
    Amount with decimals.
    """

    amount: int
    """
    An amount normalized to clearing-engine decimals.
    """

    decimals: int
    """
    An atomic amount.
    """

    def to_inventory_amount(self, rounding: str) -> int:
        return to_inventory_decimals(self.amount, self.decimals, rounding)
