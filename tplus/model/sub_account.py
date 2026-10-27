from typing import Literal

from pydantic import BaseModel, RootModel

from tplus.model.asset_identifier import AssetIdentifier


class SubAccountNameEntry(BaseModel):
    account_index: int
    name: str


class SubAccountNamesResponse(BaseModel):
    names: list[SubAccountNameEntry] = []


class RenameSubAccountResponse(BaseModel):
    account_index: int
    old_name: str
    new_name: str


class SubAccountType(
    RootModel[
        Literal["Spot", "CrossMargin"] | dict[Literal["Isolated"], dict[Literal["asset"], str]]
    ]
):
    """Kind of a new sub-account, encoded like the CE's externally tagged `SubAccountType`."""

    @classmethod
    def spot(cls) -> "SubAccountType":
        return cls("Spot")

    @classmethod
    def cross_margin(cls) -> "SubAccountType":
        return cls("CrossMargin")

    @classmethod
    def isolated(cls, asset: AssetIdentifier) -> "SubAccountType":
        return cls({"Isolated": {"asset": str(asset)}})

    @classmethod
    def from_kind(cls, kind: str, asset: AssetIdentifier) -> "SubAccountType":
        """The type named by `kind` (`Spot`, `CrossMargin`, or `Isolated` on `asset`)."""
        if kind == "Isolated":
            return cls.isolated(asset)

        return cls.model_validate(kind)
