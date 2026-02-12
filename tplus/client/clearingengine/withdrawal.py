from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.types import ChainID
from tplus.model.withdrawal import WithdrawalRequest


class WithdrawalClient(BaseClearingEngineClient):
    """
    APIs related to withdrawal.
    """

    async def init_withdrawal(self, withdrawal: dict | WithdrawalRequest):
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
        await self._post("withdrawal/init", json_data=json_data)

    async def get_signatures(self, user: str) -> list[dict]:
        """
        Get CE approved signatures for the given user for withdrawal. This happens
        after withdrawal initialization.

        Args:
            user (str): The user withdrawing.

        Returns:
            A list of approval dictionaries containing signatures, nonces, and expirys.
        """
        prefix = "withdrawal/signatures"
        result = await self._get(f"{prefix}/{user}")
        if isinstance(result, list):
            return result

        elif isinstance(result, dict) and "error" in result:
            raise RuntimeError(result["error"])

        # Unknown. Return + log whatever it is and let it fail elsewhere.
        self.logger.error(f"Unknown result format for {prefix} response: {result}.")
        return result  # type: ignore

    async def update_nonce(self, user: str, chain_id: ChainID):
        """
        Request the CE check for new completed withdrawals for the given user on
        the given chain.

        Args:
            user (str): The user withdrawing.
            chain_id (int): The chain to request withdrawals for.
        """
        await self._post(
            "admin/withdrawal/update-nonce", json_data={"user": user, "chain_id": chain_id}
        )

    async def get_queued(self, user: str) -> list[WithdrawalRequest]:
        """
        Get a user's queued withdrawals.

        Args:
            user (str): The user withdrawing.
        """
        result: list = await self._get(f"withdrawal/queue/{user}")  # type: ignore
        return [WithdrawalRequest.model_validate(d) for d in result]
