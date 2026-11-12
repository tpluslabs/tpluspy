from tplus.model.asset_identifier import AssetIdentifier

TradingAccountKind = str | dict[str, dict[str, int]]


def cross_margin() -> TradingAccountKind:
    return "CrossMargin"


def isolated(asset: AssetIdentifier | int | str) -> TradingAccountKind:
    return {"Isolated": {"asset": int(str(asset))}}
