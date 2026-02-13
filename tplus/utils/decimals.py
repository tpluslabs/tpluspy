from tplus.constants import CLEARING_ENGINE_DECIMALS


def to_inventory_decimals(amount: int, decimals: int, rounding: str) -> int:
    """
    Normalize from the given decimals to the T+ inventory decimals.
    """
    return convert_decimals(amount, decimals, CLEARING_ENGINE_DECIMALS, rounding)


def to_chain_decimals(amount: int, decimals: int, rounding: str) -> int:
    """
    Normalize from the T+ inventory decimals to the given decimals.
    """
    return convert_decimals(amount, CLEARING_ENGINE_DECIMALS, decimals, rounding)


def convert_decimals(amount: int, from_decimals: int, to_decimals: int, rounding: str) -> int:
    """
    Convert `amount` between units with different decimal places.
    Behaves like the Rust version: scales up or down depending on decimals,
    with optional round-down or ceiling division when scaling down.
    """
    round_value = rounding.lower()
    if to_decimals > from_decimals:
        # Scale up: multiply
        exponent = to_decimals - from_decimals
        factor = 10**exponent
        return amount * factor

    elif to_decimals < from_decimals:
        # Scale down: divide
        exponent = from_decimals - to_decimals
        factor = 10**exponent
        if round_value == "down":
            return amount // factor
        elif round_value == "up":
            # Ceiling division
            return (amount + factor - 1) // factor
        else:
            raise ValueError(f"Unknown rounding value '{round_value}'; expecting 'up' or 'down'.")

    else:
        # Equal, no change
        return amount
