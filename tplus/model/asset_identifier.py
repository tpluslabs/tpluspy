from dataclasses import dataclass, asdict


@dataclass
class IndexAsset:
    Index: int

    def to_dict(self):
        return asdict(self)
