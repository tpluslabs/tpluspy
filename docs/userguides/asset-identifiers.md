# Asset identifiers

T+ identifies every tradable asset with an
{py:class}`tplus.model.asset_identifier.AssetIdentifier`. This is a
**t+-specific** identifier — there is no symbol/ticker form (e.g.
`"BTC-PERP"` is **not** valid). It is one of:

1. A **registry index** — a non-negative integer assigned by the t+ asset
   registry. Compact and chain-agnostic.
2. An **`address@chain_id` string** — a 32-byte address (left-padded with
   zeros for shorter addresses like 20-byte EVM addresses) joined with a
   t+ 9-byte chain ID by `@`. Used when referring to an on-chain token
   directly.

Over JSON (REST + WebSocket) the backend sends both forms as plain
strings — `"200"` for an index, `"<address>@<chain>"` for an address.

## The chain ID format

T+ chain IDs are **9 bytes** (18 hex characters), not raw EVM chain IDs:

| Bytes | Field        | Meaning                                     |
| ----- | ------------ | ------------------------------------------- |
| 0     | `routing_id` | T+ routing tag (`0` for EVM chains)         |
| 1..8  | `vm_id`      | Native chain id (e.g. `42161` for Arbitrum) |

So Arbitrum mainnet (`42161` = `0xa4b1`) is `00000000000000a4b1` in t+
form. Build them via {py:class}`tplus.model.types.ChainID`:

```{code-block} python
from tplus.model.types import ChainID

ChainID.evm(42161)                           # routing=0, vm_id=42161
ChainID.from_parts(routing_id=1, vm_id=101)  # non-EVM routing
str(ChainID.evm(42161))                      # "00000000000000a4b1"
```

## Constructing an AssetIdentifier

```{code-block} python
from tplus.model.asset_identifier import AssetIdentifier, AssetAddress

# By registry index.
AssetIdentifier(200)
AssetIdentifier("200")  # numeric strings are accepted too.

# By raw `address@chain` string. The chain part is the 18-char hex form.
AssetIdentifier(
    "00000000000000000000000062622e77d1349face943c6e7d5c01c61465fe1dc"
    "@00000000000000a4b1"
)

# Easiest for an EVM token: build an AssetAddress and hand it to AssetIdentifier.
AssetAddress.from_evm_address(
    "0x62622E77D1349Face943C6e7D5c01C61465FE1dc",
    chain_id=42161,
)
```

`AssetIdentifier` is a Pydantic root-model wrapping a string, so passing
either an existing `AssetIdentifier` or its `str(...)` form to a client
method works interchangeably.

### `AssetAddress` vs. `ChainAddress`

`AssetAddress` and `ChainAddress` are the **same underlying type**
(`AssetAddress` is a `TypeAlias` for `ChainAddress` exported from
`tplus.model.asset_identifier`). They exist as two names so that call sites
read clearly:

- Use **`AssetAddress`** when the value is a tradable asset — building an
  `AssetIdentifier`, identifying a token in a settlement, etc.
- Use **`ChainAddress`** when the value is a non-asset chain-scoped address
  — for example a registered deposit vault, the asset registry, the
  credential-manager contract, or an MM/settler-EOA address.
  `ClearingEngineClient.vaults.get()` returns `list[ChainAddress]` for
  exactly this reason; `set_credential_manager_address(...)` accepts a
  `ChainAddress`. Most clearing-engine and EVM APIs that take "an address on
  a chain that is not an asset" are typed as `ChainAddress`.

Pick the alias that matches the *semantic role* of the value, not the
underlying class — runtime behaviour is identical.

## What does *not* work

- A symbol or ticker: `AssetIdentifier("BTC-PERP")` — there is no symbol form.
- A raw EVM chain id appended directly: `AssetIdentifier("0x...@42161")` — the
  chain part **must** be the t+ 9-byte hex form (`00000000000000a4b1`).
- An unprefixed plain hex address with no `@chain` suffix.

## Going the other way

Once you have an `AssetIdentifier` you can pull pieces out:

```{code-block} python
asset = AssetAddress.from_evm_address("0xToken...", chain_id=42161)
asset.indexed                # False — this is the address form
asset.evm_address            # checksummed 0x… EVM address (requires [evm] for checksum)
asset.chain_id               # ChainID('00000000000000a4b1')
asset.chain_id.vm_id         # 42161
```

For an indexed identifier, `.indexed` is `True` and `.evm_address` raises —
indices have no on-chain address by themselves.

## Use these everywhere

Every client method that takes an asset accepts
`AssetIdentifier | str`, but the string must match one of the forms above.
Prefer constructing a real `AssetIdentifier` (or `AssetAddress`) once and
passing it through — it avoids re-validation on every call and surfaces
format mistakes at construction time.
