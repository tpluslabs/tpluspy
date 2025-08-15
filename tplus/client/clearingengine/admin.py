from tplus.client.clearingengine.base import BaseClearingEngineClient


class AdminClient(BaseClearingEngineClient):
    async def get_verifying_key(self):
        """
        Get a clearing-engine's verifying key.

        Returns:
            str | None
        """
        return await self._get("admin/verifying-key")
