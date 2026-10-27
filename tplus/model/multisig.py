from typing import Any

from pydantic import BaseModel, SerializerFunctionWrapHandler, model_serializer, model_validator

from tplus.model.types import MultisigPermissionLevel


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
    def ed25519(cls, key_bytes: list[int]) -> "SignerKey":
        return cls(variant="Ed25519", key_bytes=key_bytes)

    @classmethod
    def secp256k1(cls, key_bytes: list[int]) -> "SignerKey":
        return cls(variant="Secp256k1", key_bytes=key_bytes)

    @classmethod
    def p256(cls, key_bytes: list[int]) -> "SignerKey":
        return cls(variant="P256", key_bytes=key_bytes)


class AdditionalSigner(BaseModel):
    signer: SignerKey
    signature: list[int]


class SignerEntry(BaseModel):
    """A registered additional signer as it appears in an account's multisig config.

    Field order matches the clearing engine's ``SignerEntry`` serde declaration, which is the
    order the config-update signing payload is verified against. An unset
    ``max_multisig_permission_level`` is omitted from the serialized form, as the clearing engine omits
    it, so the payload of a config with no capped signers is unchanged.
    """

    key: SignerKey
    weight: int
    created_at_ns: int
    expires_at_ns: int | None = None
    max_signing_window_ns: int | None = None
    max_multisig_permission_level: MultisigPermissionLevel | None = None

    @model_serializer(mode="wrap")
    def _omit_unset_permission_level(self, handler: SerializerFunctionWrapHandler) -> Any:
        data = handler(self)
        if isinstance(data, dict) and data.get("max_multisig_permission_level") is None:
            data.pop("max_multisig_permission_level", None)
        return data
