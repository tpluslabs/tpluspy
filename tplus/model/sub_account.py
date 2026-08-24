from pydantic import BaseModel


class SubAccountNameEntry(BaseModel):
    account_index: int
    name: str


class SubAccountNamesResponse(BaseModel):
    names: list[SubAccountNameEntry] = []


class RenameSubAccountResponse(BaseModel):
    account_index: int
    old_name: str
    new_name: str
