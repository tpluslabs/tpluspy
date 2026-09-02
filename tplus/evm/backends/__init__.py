from __future__ import annotations

from typing import Any

from tplus.evm.backends.base import ContractHandle, EVMBackend
from tplus.evm.exceptions import BackendNotAvailable

# Each backend module top-imports its respective optional extra and so fails
# to import here when that extra is missing -- swallow that and set a sentinel.
try:
    from tplus.evm.backends.ape import ApeBackend, ape_is_active, ape_is_available
except ImportError:
    ApeBackend = None  # type: ignore[assignment, misc]

    def ape_is_active() -> bool:
        return False

    def ape_is_available() -> bool:
        return False


try:
    from tplus.evm.backends.web3 import Web3Backend
except ImportError:
    Web3Backend = None  # type: ignore[assignment, misc]


__all__ = [
    "ContractHandle",
    "EVMBackend",
    "get_backend",
    "set_backend",
    "reset_backend",
    "resolve_backend",
    "use_ape",
    "use_web3",
    "connect",
]

_explicit_backend: EVMBackend | None = None
_auto_ape_backend: EVMBackend | None = None


def set_backend(backend: EVMBackend | None) -> None:
    """Force ``tplus.evm`` to use ``backend`` (``None`` clears it)."""
    global _explicit_backend
    _explicit_backend = backend


def reset_backend() -> None:
    """Forget any explicit and any auto-detected backend (mainly for tests)."""
    global _explicit_backend, _auto_ape_backend
    _explicit_backend = None
    _auto_ape_backend = None


def use_web3(rpc_url: str | None = None, *, web3: Any | None = None, **kwargs: Any) -> EVMBackend:
    """Use the web3.py backend, optionally bound to an explicit ``rpc_url``/``Web3``."""
    if Web3Backend is None:
        raise BackendNotAvailable('Install "tpluspy[evm]" (web3.py) to use this backend.')

    backend = Web3Backend(web3=web3, rpc_url=rpc_url, **kwargs)
    set_backend(backend)
    return backend


# Friendlier name for the common "point me at this RPC" call.
connect = use_web3


def use_ape() -> EVMBackend:
    """Use the Ape backend (requires ``tpluspy[evm-ape]`` and an active Ape network)."""
    if ApeBackend is None:
        raise BackendNotAvailable('Install "tpluspy[evm-ape]" to use this backend.')

    backend = ApeBackend()
    set_backend(backend)
    return backend


def get_backend() -> EVMBackend:
    """
    The active backend: an explicit one if set, else Ape if it's connected,
    else the web3.py backend.
    """
    if _explicit_backend is not None:
        return _explicit_backend

    if ape_is_active() and ApeBackend is not None:
        global _auto_ape_backend
        if _auto_ape_backend is None:
            _auto_ape_backend = ApeBackend()

        return _auto_ape_backend

    if Web3Backend is not None:
        return Web3Backend()

    if ape_is_available() and ApeBackend is not None:
        # Ape installed but not connected; let Ape surface its own error on use.
        return ApeBackend()

    raise BackendNotAvailable(
        'No EVM backend available. Install one with: pip install "tpluspy[evm]" '
        '(web3.py) or pip install "tpluspy[evm-ape]" (Ape).'
    )


def resolve_backend(
    backend: EVMBackend | None = None,
    *,
    rpc_url: str | None = None,
    web3: Any | None = None,
) -> EVMBackend:
    """Pick a backend for one object: ``backend=`` wins, then ``rpc_url=``/``web3=``, then :func:`get_backend`."""
    if backend is not None:
        return backend

    if rpc_url is not None or web3 is not None:
        if Web3Backend is None:
            raise BackendNotAvailable('Install "tpluspy[evm]" (web3.py) to use rpc_url=/web3=.')

        return Web3Backend(web3=web3, rpc_url=rpc_url)

    return get_backend()
