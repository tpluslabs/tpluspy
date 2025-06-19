from tplus.client.base import BaseClient
from tplus.model.withdrawal import WithdrawalRequest


class WithdrawalClient(BaseClient):
    """
    APIs related to withdrawal.
    """

    def init_withdrawal(self, withdrawal: dict | WithdrawalRequest):
        """
        Begin the steps of initializing a withdrawal. Once successful, can
        use ``.get_signatures()`` to fetch the resulting signatures for
        completing the withdrawal.

        Args:
            withdrawal (dict | WithdrawalRequest): The withdrawal data
        """
        if isinstance(withdrawal, dict):
            # Validate.
            withdrawal = WithdrawalRequest.model_validate(withdrawal)

        json_data = withdrawal.model_dump(mode="json")
        self._post("withdrawal/init", json_data=json_data)

    async def get_signatures(self, user: str) -> dict:
        """
        Get CE approved signatures for the given user for withdrawal. This happens
        after withdrawal initialization.

        Args:
            user (str): The user withdrawing.

        Returns:
            A list of signatures (rust int arrays).
        """
        return await self._get(f"withdrawal/signatures/{user}")

    async def update(self, user: str, chain_id: int):
        """
        Request the CE check for new completed deposits for the given user on
        the given chain.

        Args:
            user (str): The user withdrawing.
            chain_id (int): The chain to request withdrawals for.
        """
        await self._request("withdrawal/update", json_data={"user": user, "chain": chain_id})
