# `tplus` CLI

`tpluspy` installs a `tplus` command for interacting with T+ services from the shell.

## Global options

| Flag / Env | Purpose |
| --- | --- |
| `--account` / `TPLUS_ACCOUNT` | Default local account alias (used by signing/OMS/settle commands). |
| `--orderbook-base-url` / `TPLUS_ORDERBOOK_BASE_URL` | Orderbook/OMS service base URL. Also used by `settle` and `withdraw` (settlement & withdrawal init now go through the OMS). |
| `--clearing-base-url` / `TPLUS_CLEARING_BASE_URL` | Clearing engine base URL (admin/registry/vault commands). |
| `--market-data-base-url` / `TPLUS_MARKET_DATA_BASE_URL` | Market-data service base URL. Used by `markets depth`/`klines` and `stream trades`/`depth`/`klines`. |
| `--ignore-ssl` / `TPLUS_IGNORE_SSL` | Skip TLS certificate verification. Use for local dev with self-signed certs. |
| `--output-format` / `TPLUS_OUTPUT_FORMAT` | Output format for `list`/address commands: `table` (default), `json`, or `raw`. `raw` prints the underlying chain address string (`<address>@<chain>`) one per line; handy for piping into scripts. |
| `TPLUS_PASSWORD` | Password used to encrypt/decrypt local keyfiles, bypassing the `getpass` prompt. Intended for automation; avoid in shared shells. |

CLI logs are written to `~/.tplus/cli/logs/tplus.log` (rotating, 1 MB × 3).

Run `tplus --help` to see the top-level command list. To inspect which of these
env vars are currently set, run `tplus env`.

## Bootstrapping a local dev environment

`scripts/dev-bootstrap.sh` (in the repo root) walks a full CLI-only flow:
deploys the Registry, CredentialManager, and DepositVault; points the clearing
engine at them; registers the vault, sets the domain separator and vault
administrators; and disables the withdrawal delay. Use it as the canonical
"how do I stand up a dev environment" reference.

```shell
export TPLUS_CLEARING_BASE_URL=http://127.0.0.1:3032
export CHAIN_ID=31337                       # optional, default shown (anvil)
export APE_NETWORK=ethereum:local:foundry   # optional, default shown
export APE_ACCOUNT=TEST::0                  # optional, default shown
export TPLUS_IGNORE_SSL=1                   # optional, self-signed dev CE

./scripts/dev-bootstrap.sh
```

Token deploys, ERC20 mint/approve, and the `SettlerExecutor` helper stay in
Python (see `tpluspy/tplus/evm/dev/`) because they're test-rig concerns rather
than production ops.

## `tplus env`

Show all CLI-relevant environment variables and their current values:

```shell
tplus env
tplus env --output-format json
```

## `tplus accounts`

Manage local Ed25519 accounts stored under `~/.tplus/users`.

```shell
# Import a private key (prompts for the key if --private-key is omitted).
tplus accounts add alice --private-key <hex>

# Generate a fresh Ed25519 key.
tplus accounts generate alice

# List and inspect accounts.
tplus accounts list
tplus accounts show alice
```

## `tplus sign`

Sign a payload with a local account:

```shell
tplus sign --account alice -m "hello"
echo "hello" | tplus sign --account alice
```

## `tplus markets`

`create`/`get`/`list` talk to the orderbook (`--orderbook-base-url`); `depth`
and `klines` read from the market-data service (`--market-data-base-url`).

```shell
tplus markets create <asset_id>
tplus markets get <asset_id>
tplus markets list
tplus markets depth <asset_id>
tplus markets klines <asset_id> [--page N] [--limit N] [--end-timestamp-ns N]
```

## `tplus orders`

```shell
tplus orders place --asset <asset_id> --side buy --type limit --quantity 10 --price 1000
tplus orders place --asset <asset_id> --side sell --type market --quantity 5
tplus orders cancel <order_id> --asset <asset_id>
tplus orders replace <order_id> --asset <asset_id> --price 1050 --quantity 6
tplus orders list [--asset <asset_id>] [--open-only]
tplus orders transfer --source N --target N --asset <asset_id> --amount N
tplus orders close --account N --asset <asset_id>
```

## `tplus balance`

```shell
tplus balance [--asset-id <asset_id>]
```

## `tplus trades`

```shell
tplus trades list [--asset <asset_id>]
```

## `tplus decimals`

```shell
tplus decimals get <address> [<address> ...]
tplus decimals update <address> [<address> ...]
```

## `tplus stream`

WebSocket streams; Ctrl-C to stop. `orders` and `user-trades` stream from the
orderbook (`--orderbook-base-url`); `trades` (finalized), `depth`, and `klines`
stream from the market-data service (`--market-data-base-url`).

```shell
tplus stream orders
tplus stream trades
tplus stream depth <asset_id>
tplus stream klines <asset_id>
tplus stream user-trades [--user <pubkey>]
```

## `tplus withdraw` (alias: `tplus wd`)

Mirrors `tplus settle`. Withdrawal lifecycle now goes through the OMS
(`--orderbook-base-url`), not the CE directly: `init` signs + submits the
withdrawal request, `execute` additionally polls for the approval and submits
the on-chain `withdraw`. `init`/`execute` use Ape's `--network` / `--account`
for the on-chain signer and require `pip install "tpluspy[evm]"`. The
read/cancel subcommands (`cancel`, `list`, `signatures`) only need the OMS URL —
no `[evm]` extras.

```shell
# Sign + submit the withdrawal to the OMS (no on-chain tx yet).
tplus withdraw init --network <ape-network> --account <ape-alias> \
  --asset 0x...@42161 --amount 1000000 [--nonce N] [--target <addr>]

# Submit + on-chain withdraw once approved.
tplus withdraw execute --network <ape-network> --account <ape-alias> \
  --asset 0x...@42161 --amount 1000000 \
  [--nonce N] [--target <addr>] [--poll-interval 2] [--poll-timeout 60]

tplus wd cancel --asset 0x... --nonce N
tplus wd list [--user <pubkey>]
tplus wd signatures [--user <pubkey>] [--nonce N]
```

## `tplus assets`

Registry-owner operations. Uses Ape's `--network` / `--account` for write
paths. The read-only CE-backed subcommands (`list`, `update-ce`,
`get-registry-address`) work without the `[evm]` extras; everything that
touches the on-chain Registry (`set`, `set-risk-manager`, `deploy-registry`)
requires `pip install "tpluspy[evm]"`. When evm isn't installed, `tplus assets
list` queries the clearing engine directly and the `--ce` flag is implicit.

```shell
# List assets. Defaults to reading from the Registry contract.
tplus assets list [--network ethereum:sepolia:alchemy]

# Query the clearing engine instead:
tplus assets list --ce

# Include risk parameters per asset.
tplus assets list --include-risk-params
tplus assets list --ce --include-risk-params

# JSON output (each entry includes `index`).
tplus assets list --output-format json

tplus assets set <index> <asset_address> \
  --chain-id 42161 --max-deposit 1000000 --max-1hr 100000 --min-weight 1 \
  [--no-wait]

# Deploy a new Registry contract. Prints the deployed address.
tplus assets deploy-registry [--risk-param-delay <seconds>]

# Trigger CE re-ingestion of assets from the on-chain registry.
tplus assets update-ce

# Show the on-chain Registry address the CE is pointed at.
tplus assets get-registry-address
```

Risk parameter management lives under [`tplus params`](#tplus-params).

## `tplus params`

Manage and inspect per-asset risk parameters. `list` and `update-ce` work
against the clearing engine without the `[evm]` extras; `set` and `apply`
require `pip install "tpluspy[evm]"`.

```shell
# List risk parameters from the Registry contract (default).
tplus params list [--network ethereum:sepolia:alchemy]

# Query the clearing engine instead.
tplus params list --ce

# JSON output (each entry includes `index`).
tplus params list --output-format json

# Trigger CE re-ingestion of risk parameters from the on-chain registry.
tplus params update-ce

# Set pending risk parameters on-chain for asset INDEX.
tplus params set <index> --params '{...}'

# Apply previously-set pending risk parameters.
tplus params apply <index>
```

## `tplus withdrawal params`

On-chain withdrawal-delay parameter management. Mirrors the risk-params flow:
set pending on-chain, then trigger CE ingestion. `update-ce` works without
the `[evm]` extras; `set` requires `pip install "tpluspy[evm]"`.

```shell
# Set pending + apply withdrawal-delay params on the Registry.
tplus withdrawal params set \
  --min-delay 0 --max-delay 0 \
  --clamp 0 --clamp 1000000 \
  --value 0 --value 0 \
  [--cap-floor 50000] [--no-apply]

# Trigger CE ingestion of the on-chain params.
tplus withdrawal params update-ce
```

Prefer this over `tplus debug set-withdrawal-delay`; the debug command writes
directly to the CE state and bypasses the on-chain ingestion path.

## `tplus vaults`

Vault-owner operations. Uses Ape's `--network` / `--account` for write paths.
The read-only CE-backed subcommands (`list`, `update-ce`) work without the
`[evm]` extras; the rest (`deploy`, `deploy-registry`, `register`,
`set-administrators`, `set-domain-separator`, `set-credential-manager`,
`register-settler`, `register-depositor`, `admins`) require
`pip install "tpluspy[evm]"`. When evm isn't installed, `tplus vaults list`
queries the clearing engine directly.

```shell
# List vaults registered in the CredentialManager contract.
tplus vaults list [--network ethereum:sepolia:alchemy]

# Query the clearing engine instead.
tplus vaults list --ce

# Trigger CE re-ingestion of vaults from the on-chain credential manager.
tplus vaults update-ce

# Deploy a new CredentialManager (aka vault registry) pointing at REGISTRY.
tplus vaults deploy-registry <registry_address> \
  [--operator <addr> ...] [--quorum N] \
  [--measurement <hex> ...] [--automata-verifier <addr>]

# Deploy a new DepositVault pointing at CREDENTIAL_MANAGER.
tplus vaults deploy <credential_manager_address>

tplus vaults set-domain-separator [--separator <hex>]
tplus vaults set-administrators [--admin-key <hex> ...] [--quorum N]

# Register a vault with the credential manager (addVault).
# Default chain config is all-zeros (dev). Override any field via flags.
tplus vaults register 0x<vault>@<chain>  # or 0x<vault> --chain-id 42161
tplus vaults register 0x<vault> --chain-id 42161 \
  --block-time-ms 250 --default-confirmations 3 \
  --deposit-confirmations 3 --withdrawal-confirmations 3 \
  --settlement-confirmations 3 [--wait]

tplus vaults register-settler <alias-or-pubkey> --executor <addr> [--wait]
tplus vaults register-depositor <addr>
```

## `tplus debug`

Debug-only admin endpoints (CE must be built with the `debug-admin-endpoint`
feature). Intended for local dev and integration tests.

```shell
tplus debug set-registry-address <address> --chain-id <int>
tplus debug set-credential-manager-address <address> --chain-id <int>

# Set withdrawal delay (defaults are all-zeros / no delay).
tplus debug set-withdrawal-delay \
  [--min-delay 0] [--max-delay 0] \
  [--clamp 0 --clamp 1000000] [--value 0 --value 0] \
  [--cap-floor 50000]

# Wipe user state on the CE (handy for idempotent reruns).
tplus debug reset-users

# Seed a user's inventory in a specific sub-account.
tplus debug modify-inventory <user-pubkey> \
  --asset <id-or-address> \
  [--base-credits N] [--base-liabilities N] \
  [--quote-credits N] [--quote-liabilities N] \
  [--spot N] [--avg-spot-deposit N] \
  [--sub-account 1]
```

## `tplus deposit` *(requires `[evm]` extras)*

Deposit tokens into the vault.

```shell
tplus deposit <token> --amount 1000000000000000000 [--wait]
```

## `tplus settle`

Requires the `[evm]` extras (ape + EIP-712 deps). Commands accept Ape's
`--network` / `--account` options for the on-chain signer. Settlement init goes
through the OMS (`--orderbook-base-url`), which returns the approval
synchronously. Pass `--settler-executor <addr>` when the registered settler is a
contract (e.g. `SettlerExecutor`) rather than an EOA.

```shell
# Initialize a settlement (submits to the OMS, returns the approval).
tplus settle init \
  --network arbitrum:mainnet:alchemy --account my-ape-alias \
  --asset-in  <32-byte hex> --amount-in  1000000000000000000 --amount-in-decimals 18 \
  --asset-out <32-byte hex> --amount-out 500000               --amount-out-decimals 6

# Initialize and then execute the settlement on-chain once approved.
tplus settle execute \
  --network arbitrum:mainnet:alchemy --account my-ape-alias \
  --asset-in  <32-byte hex> --amount-in  1000000000000000000 --amount-in-decimals 18 \
  --asset-out <32-byte hex> --amount-out 500000               --amount-out-decimals 6
```
