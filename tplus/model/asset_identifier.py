from pydantic import BaseModel, model_serializer


class IndexAsset(BaseModel):
    Index: int

    @model_serializer
    def serialize_model(self) -> dict[str, int]:
        # Replicates the old {"Index": value} structure
        return {"Index": self.Index}

    def __str__(self) -> str:
        return self.Index.__str__()
