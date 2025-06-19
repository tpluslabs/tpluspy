from tplus.client.base import BaseClient


class DepositClient(BaseClient):
    """
    APIs related to deposits.
    """

    async def update(self, user: str, chain_id: int):
        """
        Request that the CE check the deposit vault for new deposits for
        the given user.

        Args:
            user (str): The user pubkey key ID.
            chain_id (int): The chain ID to check.
        """
        request = {"user": user, "chain_id": chain_id}
        await self._post("deposits/update", json_data=request)
