from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_serializer, model_validator


class SignerKey(BaseModel):
    variant: str
    key_bytes: list[int]

    @model_validator(mode="before")
    @classmethod
    def _unwrap_data(cls, data: Any) -> Any:
        if isinstance(data, dict) and len(data) == 1:
            variant = next(iter(data))
            if variant in ("Ed25519", "Secp256k1", "P256"):
                return {"variant": variant, "key_bytes": data[variant]}
        return data

    @model_serializer
    def serialize_model(self) -> dict[str, list[int]]:
        return {self.variant: self.key_bytes}

    @classmethod
    def ed25519(cls, key_bytes: list[int]) -> SignerKey:
        return cls(variant="Ed25519", key_bytes=key_bytes)

    @classmethod
    def secp256k1(cls, key_bytes: list[int]) -> SignerKey:
        return cls(variant="Secp256k1", key_bytes=key_bytes)

    @classmethod
    def p256(cls, key_bytes: list[int]) -> SignerKey:
        return cls(variant="P256", key_bytes=key_bytes)


class AdditionalSigner(BaseModel):
    signer: SignerKey
    signature: list[int]
