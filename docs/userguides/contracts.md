# Contracts

The optional EVM extra wraps the on-chain T+ contracts (`Registry`,
`DepositVault`, `CredentialManager`). The wrappers resolve deployment addresses
per chain and load the matching ABIs from a bundled manifest, so you can call
methods directly without hand-loading anything.

## Two flavors: `evm` (web3.py) and `evm-ape` (Ape)

The EVM layer runs on either [web3.py](https://web3py.readthedocs.io/) or
[Ape](https://docs.apeworx.io/ape) — pick whichever you already use:

| Install                          | Backend                       | Use it if…                                                                             |
| -------------------------------- | ----------------------------- | -------------------------------------------------------------------------------------- |
| `pip install "tpluspy[evm]"`     | web3.py                       | You just want to talk to an RPC endpoint and don't use Ape.                            |
| `pip install "tpluspy[evm-ape]"` | Ape (layered on top of `evm`) | You already work in Ape — `ape console`, account management, network configs, plugins. |

**The Python API is the same either way.** `tplus.evm.contracts.Registry` /
`DepositVault` / `CredentialManager`, the `registry` / `vault` /
`credential_manager` singletons, and the managers in `tplus.evm.managers` all
work unchanged; only which library does the chain I/O differs.

### Which backend is active?

`tplus.evm` resolves the backend lazily, the first time you actually touch a
contract:

1. If you called {py:func}`tplus.evm.use_web3` / {py:func}`tplus.evm.use_ape`
   (or {py:func}`tplus.evm.set_backend`), that wins.
2. Otherwise, if **Ape is installed and connected to a network** (e.g. inside
   `ape console` or an `ape run` script), the Ape backend is used.
3. Otherwise, the **web3.py backend** is used.

## Using the web3.py backend

Point web3.py at a node with the standard `WEB3_PROVIDER_URI` environment
variable (read by `web3.auto`):

```{code-block} shell
export WEB3_PROVIDER_URI="https://arb1.arbitrum.io/rpc"
```

```{code-block} python
from tplus.evm.contracts import registry, vault

registry.getAssets(0, 1000)
registry.admin()
vault.getApprovedSettlers()
```

Or configure it explicitly (handy for tests, multiple nodes, or a pre-built
`Web3` instance):

```{code-block} python
import tplus.evm as evm

evm.use_web3(rpc_url="https://arb1.arbitrum.io/rpc")
# or:  evm.use_web3(web3=my_web3_instance)
```

You can also override per object without touching the global default:

```{code-block} python
from tplus.evm.contracts import DepositVault
from tplus.model.types import ChainID

vault = DepositVault(
    address="0x...",
    chain_id=ChainID.evm(42161),
    rpc_url="https://arb1.arbitrum.io/rpc",
)
balance = vault.get_deposit_count(user_pubkey)
```

### Accounts (web3.py)

Anything that sends a transaction takes a `sender=` (contracts) or `account=`
(managers). With the web3.py backend that can be:

- a hex private key string,
- an [`eth_account.LocalAccount`](https://eth-account.readthedocs.io/) object, or
- on a dev node (anvil/hardhat), an unlocked-account address.

```{code-block} python
from eth_account import Account
from tplus.evm.contracts import vault

settler = Account.from_key("0x…")            # or Account.create()
vault.deposit(user_pubkey, token, amount, sender=settler)
```

## Using the Ape backend

Install the `evm-ape` extra and use Ape the way you normally would:

```{code-block} shell
pip install "tpluspy[evm-ape]"
ape console --network ethereum:sepolia:alchemy
```

Inside the console you have ready-made handles (provided by `ape_console_extras.py`):

```{code-block} python
In [1]: from tplus.evm.contracts import registry, vault, credential_manager
In [2]: registry.admin()
Out[2]: '0x467a95fC5359edE5d5dDc4f10A1F4B680694858E'
```

The Ape backend is auto-detected whenever Ape has an active provider, so the
`ape console` / `ape run` workflow is unchanged. Use Ape accounts as the
`sender=` / `account=`:

```{code-block} python
from ape import accounts
from tplus.evm.contracts import vault

eth_account = accounts.load("tplus-account")
vault.deposit(user_pubkey, token, amount, sender=eth_account)
```

`tplus.evm.contracts.TPLUS_DEPLOYMENTS` (the per-chain address map) is populated
from `~/tplus/tplus-contracts/ape-config.yaml` if present (override with
`TPLUS_CONTRACTS_PATH=`); otherwise a small built-in default is used.

## Targeting a specific deployment

```{code-block} python
from tplus.evm.contracts import DepositVault
from tplus.model.types import ChainID

vault = DepositVault(address="0x...", chain_id=ChainID.evm(42161))
count = vault.get_deposit_count(user_pubkey, account_index=0)
```

## Higher-level managers

`tplus.evm.managers` wires the CE client together with the contracts for full
flows (deposits, withdrawals, settlements, council ops). The constructors take
`account=` (a private key / `eth_account.LocalAccount` / Ape account) and an
optional `backend=`:

```{code-block} python
from tplus.evm.managers.settle import SettlementManager

mgr = SettlementManager(default_user=tplus_user, account="0x…")
await mgr.init_settlement(asset_in, amount_in, asset_out, amount_out, then_execute=True)
```

A settlement is initialized in the clearing engine (which signs the approval),
then replayed on-chain via `vault.executeAtomicSettlement(...)`; the manager
does both halves. See the [Clearing engine guide](./clearing-engine.md), and:

- {py:class}`~tplus.evm.managers.deposit.DepositManager`
- {py:class}`~tplus.evm.managers.withdraw.WithdrawalManager`
- {py:class}`~tplus.evm.managers.settle.SettlementManager`
- {py:class}`~tplus.evm.managers.vault.VaultOwner`
- {py:class}`~tplus.evm.managers.registry.RegistryOwner`
- {py:class}`~tplus.evm.managers.credential_manager.CredentialManagerOwner`

## Withdrawing on-chain

Once you have the CE-issued approvals (see [Withdrawals](./withdrawals.md)),
replay them against the vault:

```{code-block} python
receipt = vault.withdraw(
    withdrawal=request_dict,
    user=user.public_key,
    target=eth_account.address,
    valid_until=...,
    epoch_hash=...,
    signatures=[bytes.fromhex(s["signature"]) for s in approvals],
    sender=eth_account,
)
```

## Deploying for development

On a local network the wrappers will lazily deploy a development copy if no
deployment is registered:

```{code-block} python
from tplus.evm.contracts import DepositVault

vault = DepositVault.deploy_dev()
```

This is intended for tests (anvil/hardhat, or Ape's local network); production
deployments are managed via the `tplus-contracts` repo.
