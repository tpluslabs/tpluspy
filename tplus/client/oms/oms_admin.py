from tplus.client.auth import AuthenticatedClient


class OmsAdminClient(AuthenticatedClient):
    async def set_settings(
        self,
        solvency_verifier: str,
        auto_reduce_enabled: bool,
    ):
        config = {
            "solvency_verifier": solvency_verifier,
            "auto_reduce_enabled": auto_reduce_enabled,
        }

        await self._post(
            "admin/settings/modify",
            json_data=config,
        )
