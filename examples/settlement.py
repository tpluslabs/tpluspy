"""
Initiate an atomic (Tx) settlement.

Settlement *initialization* is an OMS flow: the request is signed with the t+
user's Ed25519 key and submitted to the OMS via ``OrderBookClient``. The
approval is returned directly in the ``init_settlement`` response; it can also
be re-fetched later via ``client.get_settlement_signatures(...)``.
"""

import asyncio

from tplus.client import OrderBookClient
from tplus.model.settlement import (
    InnerSettlementRequest,
    SettlementMode,
    TxSettlementRequest,
)
from tplus.model.types import ChainID
from tplus.utils.user import load_user

USERNAME = "az"

# asset_in/asset_out are 32-byte addresses on a single chain, not `address@chain`.
ASSET_IN = "0x62622E77D1349Face943C6e7D5c01C61465FE1dc"
ASSET_OUT = "0x58372ab62269A52fA636aD7F200d93999595DCAF"
CHAIN_ID = ChainID.evm(42161)
SUB_ACCOUNT = 0


async def main() -> None:
    tplus_user = load_user(USERNAME)
    client = OrderBookClient("http://127.0.0.1:8000", default_user=tplus_user)

    inner = InnerSettlementRequest.model_validate(
        {
            "mode": SettlementMode.MARGIN,
            "tplus_user": tplus_user.public_key,
            "sub_account_index": SUB_ACCOUNT,
            "asset_in": ASSET_IN,
            "amount_in": 11_478_827_000_000_000_000,
            "asset_out": ASSET_OUT,
            "amount_out": 2_500_000_000_000_000,
            "chain_id": CHAIN_ID,
        }
    )
    request = TxSettlementRequest.create_signed(inner, tplus_user)
    await client.init_settlement(request)

    approvals = await client.get_settlement_signatures(tplus_user.public_key)
    print(f"Got {len(approvals)} approval(s) from the CE.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
