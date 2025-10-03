from typing import NamedTuple


class AmountPair(NamedTuple):
    normalized: int
    """
    An amount normalized to clearing-engine decimals.
    """

    atomic: int
    """
    An atomic amount.
    """
