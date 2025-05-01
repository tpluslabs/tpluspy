"""
This file is the *magic* behind making `registry` and `deposit_vault` automatically available
in the `ape console` session.
"""

from tplus.evm.contracts import registry, vault


def ape_init_extras():
    return {
        "vault": vault,
        "registry": registry,
    }
