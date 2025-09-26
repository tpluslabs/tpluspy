from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.asset_identifier import ChainAddress
from tplus.model.settlement import BatchSettlementRequest, TxSettlementRequest


class SettlementClient(BaseClearingEngineClient):
    """
    Clearing engine APIs related to settlements.
    """

    async def init_settlement(self, request: dict | TxSettlementRequest):
        """
        Initialize a transaction (atomic) based settlement. This begins the process
        of settling. Use ``get_signatures()`` to retrieve successful signatures.

        Args:
            request (dict | TxSettlementRequest): transaction request.
        """
        if isinstance(request, dict):
            # Validate.
            request = TxSettlementRequest.model_validate(request)

        data = request.model_dump(mode="json")
        await self._post("settlement/init", json_data=data)

    async def get_signatures(self, user: str) -> dict:
        """
        Get CE approved signatures for the given user for settlement. This happens
        after settlement initialization.

        Args:
            user (str): The settler.

        Returns:
            A list of signatures (rust int arrays).
        """
        return await self._get(f"settlement/signatures/{user}")

    async def init_batch_settlement(self, request: dict | BatchSettlementRequest):
        """
        Initialize a bundle-based settlement.

        Args:
            request (dict | BatchSettlementRequest): The transaction request.
        """
        if isinstance(request, dict):
            # Validate.
            request = BatchSettlementRequest.model_validate(request)

        json_data = request.model_dump(mode="json")
        await self._post("settlement/batch", json_data=json_data)

    async def update(self, user: str, chain_id: int):
        """
        Request that the CE check the deposit vault for new settlements for
        the given user.

        Args:
            user (str): The user pubkey key ID.
            chain_id (int): The chain ID to check.
        """
        request = {"user": user, "chain_id": chain_id}
        await self._post("settlement/update", json_data=request)

    async def update_approved_settlers(self, chain_id: int, vault_address: str):
        """
        Request that the CE check the deposit vault for new approved settlers.

        Args:
            chain_id (int): The chain ID to check.
            vault_address (str): The vault address to check.
        """
        request = ChainAddress(f"{vault_address}@{chain_id}")
        json_data = request.model_dump(mode="json")
        await self._post("settlers/update", json_data=json_data)

    async def get_approved_settlers(self, chain_id: int) -> list[str]:
        """
        Request that the CE check the deposit vault for new approved settlers.

        Args:
            chain_id (int): The chain ID to check.
        """
        return await self._get(f"settlers/{chain_id}")  # type: ignore
