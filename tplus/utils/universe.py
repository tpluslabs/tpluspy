from enum import Enum

from eth_pydantic_types.hex.bytes import HexBytes32
from eth_utils import keccak

DEV_UNIVERSE_PREFIX = "tplus-dev-"
DEV_UNIVERSE_ENVIRONMENT = "local"


def compute_universe_id(name: str) -> HexBytes32:
    """Governance universe ID of a universe name, the `salt` of the governance signing domain."""
    return HexBytes32(keccak(text=name))


def build_dev_universe_name(environment: str) -> str:
    """Universe name of one developer environment."""
    return f"{DEV_UNIVERSE_PREFIX}{environment}"


class Universe(str, Enum):
    """A named governance universe; developer environments use `build_dev_universe_name`."""

    MAINNET = "tplus-mainnet"
    STAGING = "tplus-staging"

    @property
    def id(self) -> HexBytes32:
        return compute_universe_id(self.value)
