"""Stand-in representation-rate providers for local chains.

The rate readers in the chain adapter decode real provider layouts, so exercising them end to end
needs contracts that answer those calls. ``RepresentationRateMocks.sol`` holds the reduced sources
and ``representation_rate_mocks.json`` the compiled output, checked in so a test chain needs no
Solidity compiler. That ABI carries only the entries a caller here drives; the provider state is
read by the clearing engine over RPC, against its own bindings.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_MOCKS_PATH = Path(__file__).parent / "representation_rate_mocks.json"

ONDO_SHARES_ORACLE = "MockOndoSharesOracle"
BACKED_AUTO_FEE_TOKEN = "MockBackedAutoFeeToken"


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    return json.loads(_MOCKS_PATH.read_text())


def _mock(name: str) -> dict[str, Any]:
    mocks = _load()
    try:
        return mocks[name]

    except KeyError as err:
        raise KeyError(
            f"Mock '{name}' is not compiled in. Available: {', '.join(sorted(mocks))}."
        ) from err


def get_abi(name: str) -> list[dict[str, Any]]:
    """The ABI for the named mock provider."""
    return list(_mock(name)["abi"])


def get_deployment_bytecode(name: str) -> bytes:
    """The creation bytecode for the named mock provider."""
    return bytes.fromhex(_mock(name)["bin"].removeprefix("0x"))
