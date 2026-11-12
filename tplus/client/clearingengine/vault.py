from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.asset_identifier import ChainAddress
from tplus.model.vault import ChildManager


class VaultClient(BaseClearingEngineClient):
    """
    APIs related to vaults.
    """

    async def update(self):
        """
        Request that the CE check the registry contract for new registered vaults.
        """
        await self._post("vaults/update")

    async def update_child_managers(self):
        """
        Request that the CE re-read the child credential managers its credential manager lists.
        """
        await self._post("child-managers/update")

    async def get_child_managers(self) -> list[ChildManager]:
        """
        Get the child credential managers the CE's credential manager lists.
        """
        return [ChildManager.model_validate(entry) for entry in await self._get("child-managers")]

    async def set_credential_manager_address(self, credential_manager: ChainAddress):
        """
        Admin-only endpoint for setting the credential manager address. Used in testing environment.
        """
        payload = credential_manager.model_dump()
        await self._post("admin/credential-manager/update-address", json_data=payload)
