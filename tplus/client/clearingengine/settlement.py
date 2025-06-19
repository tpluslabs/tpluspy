from tplus.client.base import BaseClient
from tplus.model.settlement import BundleSettlementRequest, TxSettlementRequest


class SettlementClient(BaseClient):
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

        data = request.model_dump()
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

    async def init_bundle_settlement(self, request: dict | BundleSettlementRequest):
        """
        Initialize a bundle-based settlement.

        Args:
            request (dict | BundleSettlementRequest): The transaction request.
        """
        if isinstance(request, dict):
            # Validate.
            request = BundleSettlementRequest.model_validate(request)

        json_data = request.model_dump(mode="json")
        await self._post("settlement/init-bundle", json_data=json_data)
