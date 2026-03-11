from pydantic import BaseModel


class InterestRates(BaseModel):
    asset_identifier: str
    funding_rate: int
    utilisation_rate: int
    quote_utilisation_rate: int
