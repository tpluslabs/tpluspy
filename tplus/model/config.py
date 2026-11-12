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

    @classmethod
    def for_evm_chain(cls, chain_id: int) -> "ChainConfig | None":
        """The confirmation policy production runs for an EVM chain, or ``None`` for others."""
        # TODO: read these from one source shared with infra's chain values and `AddVault.s.sol`.
        policies = {
            1: (12_000, 4),
            42_161: (1_000, 15),
            143: (400, 15),
            8_453: (2_000, 10),
        }
        if chain_id not in policies:
            return None

        block_time_ms, confirmations = policies[chain_id]
        return cls(
            blockTimeMs=block_time_ms,
            defaultConfirmations=confirmations,
            depositIngestConfirmations=confirmations,
            withdrawalIngestConfirmations=confirmations,
            settlementIngestConfirmations=0,
        )

    def find_unexpected_zero_confirmations(self, expected: "ChainConfig | None") -> list[str]:
        """Confirmation fields that are zero although ``expected`` does not make them zero."""
        names = (
            "defaultConfirmations",
            "depositIngestConfirmations",
            "withdrawalIngestConfirmations",
            "settlementIngestConfirmations",
        )
        return [
            name
            for name in names
            if getattr(self, name) == 0 and (expected is None or getattr(expected, name) != 0)
        ]

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
        try:
            # Have to do this inline since it is not in the evm namespace.
            from eth_abi import encode  # type: ignore
        except ImportError:
            raise ValueError("Install [evm] extras to use abi-encoding feature")

        return encode(self.abi_types, self.abi_values)
