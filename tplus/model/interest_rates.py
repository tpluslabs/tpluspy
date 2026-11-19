from pydantic import BaseModel


class InterestRates(BaseModel):
    asset: int
    funding_rate: int
    borrow_rate: int
    quote_borrow_rate: int
