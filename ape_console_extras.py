"""
This file is the *magic* behind making `registry` and `deposit_vault` automatically available
in the `ape console` session.
"""

import os

from tplus.evm.contracts import registry, vault


def ape_init_extras():
    res: dict = {
        "vault": vault,
        "registry": registry,
    }

    try:
        from ape import chain

        from tplus.client import ClearingEngineClient
        from tplus.utils.user import load_user

        if chain.provider.network.is_dev:
            if tplus_user := load_user(password=os.environ.get("TPLUSPY_USER_PASSWORD")):
                clearing_engine = ClearingEngineClient(tplus_user, "http://127.0.0.1:3032")
                res["ce"] = clearing_engine
                res["tplus_user"] = tplus_user

        else:
            res["load_user"] = load_user
            res["ClearingEngineClient"] = ClearingEngineClient

    except Exception as err:
        # Don't let this nonsense crash the session.
        print(f"Error from loading ape console extras: {err}")

    return res
