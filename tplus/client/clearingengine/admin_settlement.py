from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.chain_address import ChainAddress
from tplus.model.types import ChainID, UserPublicKey


class AdminSettlementClient(BaseClearingEngineClient):
    """
    Clearing engine APIs related to settlements.

    Settlement *initialization* and approval retrieval are OMS flows (see
    :class:`tplus.client.OrderBookClient`); this client only covers the CE-side
    nonce/settler refresh endpoints.
    """

    async def update_approved_settlers(self, vaults: ChainAddress | list[ChainAddress]):
        """
        Request that the CE refresh approved settlers for the named vault(s).

        Each vault is a full :class:`ChainAddress` (carrying its own chain), so
        a single call may refresh vaults across multiple chains. Every vault
        must be registered in the CE's trusted vault registry.

        Args:
            vaults: A registered vault address, or a list of them.
        """
        if isinstance(vaults, ChainAddress):
            vaults = [vaults]
        json_data = {"vaults": [str(v) for v in vaults]}
        await self._post("settlers/update", json_data=json_data)

    async def get_approved_settlers(self, chain_id: ChainID) -> dict[str, list[UserPublicKey]]:
        """
        Get the approved settlers for a chain, keyed by registered vault
        address (32-byte hex). The latest-registered vault is the default a
        settlement executes against when its request names no vault.

        Args:
            chain_id (ChainID): The chain ID to check.
        """
        result = await self._get(f"settlers/{chain_id}")  # type: ignore
        return {
            vault: [UserPublicKey.__validate_user__(s) for s in settlers]
            for vault, settlers in result.items()
        }
