"""
This file is the *magic* behind making `registry` and `deposit_vault` automatically available
in the `ape console` session.
"""

from tplus.contracts import DepositVault, Registry


def ape_init_extras(chain):
    return {
        "vault": DepositVault(),
        "registry": Registry(),
    }
