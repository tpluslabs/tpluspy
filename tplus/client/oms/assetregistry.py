from collections.abc import Sequence

from tplus.client.auth import AuthenticatedClient
from tplus.model.asset_identifier import AssetAddress
from tplus.model.chain_address import ChainAddress
from tplus.model.representation_rate import RepresentationRatesResponse
from tplus.model.vault import RebalancingBacking


def _prep_request(assets: Sequence[str | AssetAddress]) -> dict:
    payload_assets: list[dict] = []
    for asset in assets:
        if isinstance(asset, AssetAddress):
            # Already validated.
            payload_assets.append(asset.model_dump())
        else:
            payload_assets.append(AssetAddress.model_validate(asset).model_dump())

    return {"assets": payload_assets}


class AssetRegistryClient(AuthenticatedClient):
    """
    Public OMS APIs for registry snapshots received from CE.
    """

    async def get_asset_config(self) -> dict:
        """
        Get the current asset config map (`GET /registry/assets`).
        """
        return await self._get("registry/assets", requires_auth=False)

    async def get_representation_rates(self) -> RepresentationRatesResponse:
        """
        Get the rates the CE is converting representation tokens at
        (`GET /registry/representation-rates`).
        """
        response = await self._get("registry/representation-rates", requires_auth=False)
        return RepresentationRatesResponse.model_validate(response)

    async def get_risk_parameters(self) -> dict:
        """
        Get the current risk parameter map (`GET /registry/risk-parameters`).
        """
        return await self._get("registry/risk-parameters", requires_auth=False)

    async def get_netting_parameters(self) -> list[dict]:
        """
        Get the asset-netting table OMS is pricing against
        (`GET /registry/netting-parameters`).

        Rows are `{asset, venue, venue_asset, cost, residual,
        margin_call_timeout_ns, allowance}`: `asset` and `venue_asset` are canonical
        integer indices; `cost` and `residual` ppm-encoded,
        `margin_call_timeout_ns` the pair's margin-call grace period (`0` grants
        none), and `allowance` the shared offset allowance of a venue row as a
        decimal string in inventory units (`"0"` grants none). An empty list means the table is synced and no
        offsetting is configured; a 503 means OMS has not received one from the
        clearing engine yet, and raises.
        """
        response = await self._get("registry/netting-parameters", requires_auth=False)
        if not isinstance(response, list):
            raise TypeError(f"Expected list response for netting parameters, got: {type(response)}")
        return response

    async def get_rebalancing_backing(self) -> list[RebalancingBacking]:
        """
        Get every token's rebalancing anchor, backing and vault balances at 18 decimals, as the
        clearing engine gossips them (`GET /registry/rebalancing-backing`). A 503 means OMS has
        not received them yet, and raises.
        """
        response = await self._get("registry/rebalancing-backing", requires_auth=False)
        if not isinstance(response, list):
            raise TypeError(
                f"Expected list response for rebalancing backing, got: {type(response)}"
            )
        return [RebalancingBacking.model_validate(entry) for entry in response]

    async def get_venue_fade_parameters(self) -> list[dict]:
        """
        Get the venue fade table OMS is pricing against
        (`GET /registry/venue-fade-parameters`).

        Rows are `{venue, horizon_secs, step_secs, exponent}`: a state-locked
        venue keeps `1 - (stepped lock age / horizon_secs)^exponent` of its
        value and of its netting offer, the age moving in whole `step_secs`. An
        empty list means the table is synced and every venue fades on the
        default curve (2700 s, 300 s, 3); a 503 means OMS has not received one
        from the clearing engine yet, and raises.
        """
        response = await self._get("registry/venue-fade-parameters", requires_auth=False)
        if not isinstance(response, list):
            raise TypeError(
                f"Expected list response for venue fade parameters, got: {type(response)}"
            )
        return response

    async def get_asset_decimals(self, assets: list[str | AssetAddress]) -> dict:
        """
        Get cached decimals for the given assets (`POST /registry/decimals`).
        """
        return await self._post(
            "registry/decimals",
            json_data=_prep_request(assets),
            requires_auth=False,
        )

    async def update_asset_decimals(self, assets: list[str | AssetAddress]) -> None:
        """
        Trigger decimals refresh (`POST /registry/decimals/update`).
        Note: max asset count per request is 100
        """
        await self._post(
            "registry/decimals/update",
            json_data=_prep_request(assets),
            requires_auth=True,
        )

    async def get_vaults(self) -> list[ChainAddress]:
        """
        Get vault addresses (`GET /registry/vaults`).
        """
        response = await self._get("registry/vaults", requires_auth=False)
        if not isinstance(response, list):
            raise TypeError(f"Expected list response for registry vaults, got: {type(response)}")
        return [ChainAddress.model_validate(v) for v in response]
