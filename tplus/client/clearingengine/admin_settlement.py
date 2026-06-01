from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.asset_identifier import ChainAddress
from tplus.model.types import ChainID, UserPublicKey


class AdminSettlementClient(BaseClearingEngineClient):
    """
    Clearing engine APIs related to settlements.

    Settlement *initialization* and approval retrieval are OMS flows (see
    :class:`tplus.client.OrderBookClient`); this client only covers the CE-side
    nonce/settler refresh endpoints.
    """

    async def update_approved_settlers(self, chain_id: ChainID, vault_address: str):
        """
        Request that the CE check the deposit vault for new approved settlers.

        Args:
            chain_id (int): The chain ID to check.
            vault_address (str): The vault address to check.
        """
        request = ChainAddress.from_str(f"{vault_address}@{chain_id}")
        json_data = request.model_dump(mode="json")
        await self._post("settlers/update", json_data=json_data)

    async def get_approved_settlers(self, chain_id: ChainID) -> list[UserPublicKey]:
        """
        Request that the CE check the deposit vault for new approved settlers.

        Args:
            chain_id (int): The chain ID to check.
        """
        result = await self._get(f"settlers/{chain_id}")  # type: ignore
        return [UserPublicKey.__validate_user__(s) for s in result]
