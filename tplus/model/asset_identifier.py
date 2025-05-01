from dataclasses import asdict, dataclass


@dataclass
class IndexAsset:
    Index: int

    def to_dict(self):
        return asdict(self)
