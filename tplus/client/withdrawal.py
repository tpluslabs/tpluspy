from tplus.client.auth import AuthenticatedClient
from tplus.exceptions import OmsError
from tplus.model.withdrawal import CancelWithdrawalRequest, WithdrawalRequest

# OMS `CE_WITHDRAWAL_QUEUE_READ_WAIT` is 15s; default httpx client timeout is 10s — queue polls would ReadTimeout early.
_QUEUE_HTTP_TIMEOUT_SEC = 30.0


class WithdrawalClient(AuthenticatedClient):
    """OMS-facing APIs for withdrawal lifecycle operations."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        **kwargs,
    ) -> None:
        super().__init__(base_url, **kwargs)

    async def init_withdrawal(self, withdrawal: dict | WithdrawalRequest) -> None:
        if isinstance(withdrawal, dict):
            withdrawal = WithdrawalRequest.model_validate(withdrawal)

        json_data = withdrawal.model_dump(mode="json")
        try:
            response = await self._post("withdrawal/init", json_data=json_data)
        except OmsError as err:
            if err.code != "TIMEOUT_UNKNOWN_STATE":
                raise
            return
        if isinstance(response, dict) and response.get("success") is False:
            reason = response.get("details") or "Withdrawal initialization failed"
            raise RuntimeError(str(reason))

    async def cancel_withdrawal(self, cancel_request: dict | CancelWithdrawalRequest) -> None:
        if isinstance(cancel_request, dict):
            cancel_request = CancelWithdrawalRequest.model_validate(cancel_request)
        json_data = cancel_request.model_dump(mode="json")
        await self._post("withdrawal/cancel", json_data=json_data)

    async def get_queued_withdrawals(self, user: str) -> list[dict]:
        result = await self._get(
            f"withdrawal/queue/{user}", request_timeout=_QUEUE_HTTP_TIMEOUT_SEC
        )
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "error" in result:
            raise RuntimeError(result["error"])
        self.logger.error(f"Unknown result format for withdrawal queue response: {result}.")
        return result  # type: ignore[return-value]
