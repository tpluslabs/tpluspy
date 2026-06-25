from functools import cached_property
from typing import TYPE_CHECKING

from tplus.client.clearingengine.admin import AdminClient
from tplus.client.clearingengine.admin_settlement import AdminSettlementClient
from tplus.client.clearingengine.assetregistry import AdminAssetRegistryClient
from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.client.clearingengine.cross_venue import CrossVenueClient
from tplus.client.clearingengine.decimal import DecimalClient
from tplus.client.clearingengine.vault import VaultClient

if TYPE_CHECKING:
    from tplus.utils.user import User


class ClearingEngineClient(BaseClearingEngineClient):
    """
    APIs targeting the clearing engine ("CE") directly. Most of the APIs are
    permission-less; however some require signing, such as settlements and withdrawal flows.
    """

    @classmethod
    def from_local(cls, user: "User", port: int = 3032, **kwargs):
        return cls(base_url=f"http://127.0.0.1:{port}", default_user=user, **kwargs)

    @cached_property
    def admin_settlements(self) -> AdminSettlementClient:
        """
        APIs related to settlements.
        """
        return AdminSettlementClient.from_client(self)

    @cached_property
    def assets(self) -> AdminAssetRegistryClient:
        """
        Admin APIs related to registered assets.
        """
        return AdminAssetRegistryClient.from_client(self)

    @cached_property
    def decimals(self) -> DecimalClient:
        """
        APIs related to decimals.
        """
        return DecimalClient.from_client(self)

    @cached_property
    def vaults(self) -> VaultClient:
        """
        APIs related to vaults.
        """
        return VaultClient.from_client(self)

    @cached_property
    def cross_venue(self) -> CrossVenueClient:
        """
        User-facing cross-venue (Hyperliquid) margin APIs.
        """
        return CrossVenueClient.from_client(self)

    @cached_property
    def admin(self) -> AdminClient:
        """
        APIs related to the admin clearing-engine.
        """
        return AdminClient.from_client(self)
