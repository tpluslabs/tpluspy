"""
This file is the *magic* behind making `registry` and `deposit_vault` automatically available
in the `ape console` session.
"""

from tplus.contracts import registry


def ape_init_extras():
    return {
        "vault": deposit_vault,
        "registry": registry,
    }
