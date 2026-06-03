from tplus.model.risk_parameters import RiskParameters


def _risk_params_payload() -> dict:
    return {
        "collateralFactor": 75,
        "liabilityFactor": 50,
        "maxCollateral": 1_000_000,
        "maxOpenInterest": 2_000_000,
        "maxSpotOpenInterest": 3_000_000,
        "maxUtilization": 800_000_000_000_000_000,
        "isolatedOnly": False,
        "interestKinks": [0, 1_000_000],
        "kinkInterestRates": [0, 1_000_000],
        "usdInterestKinks": [0, 1_000_000],
        "usdKinkInterestRates": [0, 1_000_000],
        "skewModifier": 9_000,
        "skewCliff": 500,
        "baseFundingRate": 500,
        "premiumClamp": 500,
        "initialMarginClamps": [0, 500_000],
        "initialMarginFactors": [980_000, 0],
        "maxFundingRate": 1_000,
        "maxUtilizationRate": 1_000,
        "bufferMultiple": 1_200_000,
    }


def test_defaults_min_sub_account_balance_to_zero():
    params = RiskParameters.model_validate(_risk_params_payload())
    assert params.min_sub_account_balance == 0


def test_serializes_min_sub_account_balance_alias():
    payload = _risk_params_payload()
    payload["minSubAccountBalance"] = 42
    params = RiskParameters.model_validate(payload)
    dumped = params.model_dump(by_alias=True)
    assert dumped["minSubAccountBalance"] == 42
