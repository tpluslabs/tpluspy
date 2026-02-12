from eth_abi import encode
from pydantic import BaseModel


class ChainConfig(BaseModel):
    """
    Configure chains in the vault registry.
    """

    blockTimeMs: int
    """
    Approximate block time in milliseconds.
    """

    defaultConfirmations: int
    """
    The default amount of confirmations to wait for an event to ingest.
    """

    depositIngestConfirmations: int
    """
    The amount of confirmations to wait for a deposit to ingest.
    """

    withdrawalIngestConfirmations: int
    """
    The amount of confirmations to wait for a withdrawal to ingest.
    """

    settlementIngestConfirmations: int
    """
    The amount of confirmations to wait for a settlement to ingest.
    """

    @classmethod
    def dev(cls) -> "ChainConfig":
        return cls(
            blockTimeMs=0,
            defaultConfirmations=0,
            depositIngestConfirmations=0,
            withdrawalIngestConfirmations=0,
            settlementIngestConfirmations=0,
        )

    @property
    def abi_types(self) -> list[str]:
        return [
            "uint64",
            "uint8",
            "uint8",
            "uint8",
            "uint8",
        ]

    @property
    def abi_values(self) -> tuple[int, int, int, int, int]:
        return (
            self.blockTimeMs,
            self.defaultConfirmations,
            self.depositIngestConfirmations,
            self.withdrawalIngestConfirmations,
            self.settlementIngestConfirmations,
        )

    def abi_encode(self) -> bytes:
        """
        Full ABI encoding of the struct
        equivalent to abi.encode(ChainConfig).
        """
        return encode(self.abi_types, self.abi_values)
