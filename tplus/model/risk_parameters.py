from pydantic import BaseModel, ConfigDict, Field


class RiskParameters(BaseModel):
    """
    Mirror of `Registry.RiskParameters` from tplus-contracts.

    Field names use snake_case in Python; aliases match the Solidity struct so
    `model_dump(by_alias=True)` produces a dict that ape will encode against the
    contract ABI directly.
    """

    model_config = ConfigDict(populate_by_name=True)

    collateral_factor: int = Field(alias="collateralFactor")
    liability_factor: int = Field(alias="liabilityFactor")
    max_collateral: int = Field(alias="maxCollateral")
    max_open_interest: int = Field(alias="maxOpenInterest")
    max_spot_open_interest: int = Field(alias="maxSpotOpenInterest")
    max_utilization: int = Field(alias="maxUtilization")
    isolated_only: bool = Field(alias="isolatedOnly")
    interest_kinks: list[int] = Field(alias="interestKinks")
    kink_interest_rates: list[int] = Field(alias="kinkInterestRates")
    usd_interest_kinks: list[int] = Field(alias="usdInterestKinks")
    usd_kink_interest_rates: list[int] = Field(alias="usdKinkInterestRates")
    skew_modifier: int = Field(alias="skewModifier")
    skew_cliff: int = Field(alias="skewCliff")
    base_funding_rate: int = Field(alias="baseFundingRate")
    premium_clamp: int = Field(alias="premiumClamp")
    initial_margin_clamps: list[int] = Field(alias="initialMarginClamps")
    initial_margin_factors: list[int] = Field(alias="initialMarginFactors")
    max_funding_rate: int = Field(alias="maxFundingRate")
    max_utilization_rate: int = Field(alias="maxUtilizationRate")
    buffer_multiple: int = Field(alias="bufferMultiple")
