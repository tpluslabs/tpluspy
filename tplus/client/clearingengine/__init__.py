from functools import cached_property

from tplus.client.clearingengine.assetregistry import AssetRegistryClient
from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.client.clearingengine.decimal import DecimalClient
from tplus.client.clearingengine.deposit import DepositClient
from tplus.client.clearingengine.settlement import SettlementClient
from tplus.client.clearingengine.vault import VaultClient
from tplus.client.clearingengine.withdrawal import WithdrawalClient


class ClearingEngineClient(BaseClearingEngineClient):
    """
    APIs targeting the clearing engine ("CE") directly. Most of the APIs are
    permission-less; however some require signing, such as settlements and withdrawal flows.
    """

    @cached_property
    def settlements(self) -> SettlementClient:
        """
        APIs related to settlements.
        """
        return SettlementClient.from_client(self)

    @cached_property
    def assets(self) -> AssetRegistryClient:
        """
        APIs related to registered assets.
        """
        return AssetRegistryClient.from_client(self)

    @cached_property
    def decimals(self) -> DecimalClient:
        """
        APIs related to decimals.
        """
        return DecimalClient.from_client(self)

    @cached_property
    def deposits(self) -> DepositClient:
        """
        APIs related to deposits.
        """
        return DepositClient.from_client(self)

    @cached_property
    def withdrawals(self) -> WithdrawalClient:
        """
        APIs related to withdrawals.
        """
        return WithdrawalClient.from_client(self)

    @cached_property
    def vaults(self) -> VaultClient:
        """
        APIs related to vaults.
        """
        return VaultClient.from_client(self)
