from tplus.constants import CLEARING_ENGINE_DECIMALS


def normalize_to_inventory(amount: int, decimals: int, rounding: str) -> int:
    """
    Normalize from the given decimals to the T+ inventory decimals.
    """
    return normalize_decimals(amount, decimals, CLEARING_ENGINE_DECIMALS, rounding)


def normalize_from_inventory(amount: int, decimals: int, rounding: str) -> int:
    """
    Normalize from the T+ inventory decimals to the given decimals.
    """
    return normalize_decimals(amount, CLEARING_ENGINE_DECIMALS, decimals, rounding)


def normalize_decimals(amount: int, from_decimals: int, to_decimals: int, rounding: str) -> int:
    """
    Convert `amount` between units with different decimal places.
    Behaves like the Rust version: scales up or down depending on decimals,
    with optional round-down or ceiling division when scaling down.
    """
    round_down = rounding.lower() == "down"
    if to_decimals > from_decimals:
        # Scale up: multiply
        exponent = to_decimals - from_decimals
        factor = 10**exponent
        return amount * factor

    elif to_decimals < from_decimals:
        # Scale down: divide
        exponent = from_decimals - to_decimals
        factor = 10**exponent
        if round_down:
            return amount // factor
        else:
            # Ceiling division
            return (amount + factor - 1) // factor

    else:
        # Equal, no change
        return amount
