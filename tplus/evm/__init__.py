"""On-chain (EVM) integration -- runs on web3.py (``tpluspy[evm]``) or Ape (``tpluspy[evm-ape]``)."""

from tplus.evm.backends import (
    connect,
    get_backend,
    reset_backend,
    set_backend,
    use_ape,
    use_web3,
)

__all__ = [
    "connect",
    "get_backend",
    "reset_backend",
    "set_backend",
    "use_ape",
    "use_web3",
]
