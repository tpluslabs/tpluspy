from pydantic import BaseModel, Field

from tplus.model.multisig import AdditionalSigner


class AuthRequestBody(BaseModel):
    """Request body for `POST /auth`."""

    user_id: str
    nonce: str
    signature: list[int]
    additional_signers: list[AdditionalSigner] = Field(default_factory=list)


class AuthTokenResponse(BaseModel):
    """Bearer token from `POST /auth`."""

    token: str
    expiry_ns: int
