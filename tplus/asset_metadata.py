"""Static T+ asset metadata used for display-only symbol resolution.

The protocol identifies assets by ``AssetIdentifier`` values, not symbols. This
module is a temporary local snapshot so CLI and onboarding output can show the
canonical symbol next to known production indexes and chain-address aliases.

Source snapshot: ``tplus-risk-params`` ``main:environments/prod/params.json``.
Do not use this for risk checks; read live registry/market endpoints for trading
parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tplus.model.asset_identifier import AssetIdentifier


@dataclass(frozen=True)
class AssetMetadata:
    index: int
    symbol: str
    asset_class: str
    representations: tuple[str, ...]


CANONICAL_ASSETS: dict[int, AssetMetadata] = {
    0: AssetMetadata(0, "USDC", "USD", ("USDC", "USDT")),
    1: AssetMetadata(1, "ETH", "ETH", ("WETH",)),
    2: AssetMetadata(2, "BTC", "BTC", ("WBTC",)),
    3: AssetMetadata(3, "ARB", "ARB", ("ARB",)),
    4: AssetMetadata(4, "MON", "MON", ("MON",)),
    5: AssetMetadata(5, "GOLD", "GOLD", ("XAUT",)),
    6: AssetMetadata(6, "CIGS", "CIGS", ("CIGS",)),
}


CHAIN_ASSET_INDEXES: dict[str, int] = {
    # USDC / USDT -> USD class.
    "a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48000000000000000000000000@000000000000000001": 0,
    "af88d065e77c8cc2239327c5edb3a432268e5831000000000000000000000000@00000000000000a4b1": 0,
    "754704bc059f8c67012fed69bc8a327a5aafb603000000000000000000000000@00000000000000008f": 0,
    "dac17f958d2ee523a2206206994597c13d831ec7000000000000000000000000@000000000000000001": 0,
    "833589fcd6edb6e08f4c7c32d4f71b54bda02913000000000000000000000000@000000000000002105": 0,
    # ETH.
    "82af49447d8a07e3bd95bd0d56f35241523fbab1000000000000000000000000@00000000000000a4b1": 1,
    "c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2000000000000000000000000@000000000000000001": 1,
    "ee8c0e9f1bffb4eb878d8f15f368a02a35481242000000000000000000000000@00000000000000008f": 1,
    "4200000000000000000000000000000000000006000000000000000000000000@000000000000002105": 1,
    # BTC.
    "2260fac5e5542a773aa44fbcfedf7c193bc2c599000000000000000000000000@000000000000000001": 2,
    "2f2a2543b76a4166549f7aab2e75bef0aefc5b0f000000000000000000000000@00000000000000a4b1": 2,
    "0555e30da8f98308edb960aa94c0db47230d2b9c000000000000000000000000@00000000000000008f": 2,
    # ARB.
    "b50721bcf8d664c30412cfbc6cf7a15145234ad1000000000000000000000000@000000000000000001": 3,
    "912ce59144191c1204e64559fe8253a0e49e6548000000000000000000000000@00000000000000a4b1": 3,
    # MON.
    "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee000000000000000000000000@00000000000000008f": 4,
    # GOLD / XAUT.
    "68749665ff8d2d112fa859aa293f07a622782f38000000000000000000000000@000000000000000001": 5,
    # CIGS.
    "2e9126f66e386879f312287a419b0f70004c3f5b000000000000000000000000@000000000000002105": 6,
}


def _asset_id_key(asset_id: Any) -> str:
    if isinstance(asset_id, AssetIdentifier):
        return str(asset_id)
    if isinstance(asset_id, int):
        return str(asset_id)
    if isinstance(asset_id, dict):
        return str(AssetIdentifier.model_validate(asset_id))
    return str(asset_id).lower().removeprefix("0x")


def asset_index(asset_id: Any) -> int | None:
    """Return the canonical asset index for a known index/address identifier."""
    key = _asset_id_key(asset_id)
    if key.isnumeric():
        return int(key)
    if "@" in key:
        try:
            key = str(AssetIdentifier(key))
        except ValueError:
            pass
        return CHAIN_ASSET_INDEXES.get(key)
    return None


def get_asset_metadata(asset_id: Any) -> AssetMetadata | None:
    index = asset_index(asset_id)
    if index is None:
        return None
    return CANONICAL_ASSETS.get(index)


def asset_label(asset_id: Any) -> str:
    """Human label for a known asset identifier, falling back without guessing."""
    key = _asset_id_key(asset_id)
    metadata = get_asset_metadata(key)
    if metadata is None:
        return f"asset {key}"
    return f"{metadata.symbol} (asset {key})"


def asset_metadata_dict(asset_id: Any) -> dict[str, Any] | None:
    metadata = get_asset_metadata(asset_id)
    if metadata is None:
        return None
    return {
        "index": metadata.index,
        "symbol": metadata.symbol,
        "asset_class": metadata.asset_class,
        "representations": list(metadata.representations),
    }
