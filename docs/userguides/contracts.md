# Contracts

The optional `evm` extra wraps the on-chain T+ contracts via
[Ape](https://docs.apeworx.io/ape). The wrappers automatically resolve
deployment addresses (per chain) and load the matching ABIs from a bundled
manifest, so you can call methods directly without hand-loading addresses.

## Install

```{code-block} shell
pip install "tpluspy[evm]"
```

## Connecting

Launch an Ape console connected to your network of choice:

```{code-block} shell
ape console --network ethereum:sepolia:alchemy
```

Inside the console you have access to ready-made contract handles:

```{code-block} python
In [1]: from tplus.evm.contracts import registry, vault, credential_manager
In [2]: registry.getAssets()
Out[2]: [getAssets_return(assetAddress=HexBytes('0x...'), chainId=11155111, maxDeposits=100)]
In [3]: registry.admin()
Out[3]: '0x467a95fC5359edE5d5dDc4f10A1F4B680694858E'
```

The default `registry`, `vault`, and `credential_manager` instances pick up
their address from {py:data}`tplus.evm.contracts.TPLUS_DEPLOYMENTS`, which is
populated from `~/tplus/tplus-contracts/ape-config.yaml` if present (override
with `TPLUS_CONTRACTS_PATH=`).

## Targeting a specific deployment

```{code-block} python
from tplus.evm.contracts import DepositVault
from tplus.model.types import ChainID

vault = DepositVault(
    address="0x...",
    chain_id=ChainID.evm(42161),
)
balance = vault.get_deposit_count(user_pubkey)
```

## Settlement signatures

Settlement messages are signed by an Ethereum account using the structured
`Order` type from {py:mod}`tplus.utils.domain`:

```{code-block} python
from ape import accounts, chain, convert

from tplus.evm.contracts import vault
from tplus.utils.domain import Order
from tplus.utils.user import UserManager

# Load your Ethereum account that signs settlements.
eth_account = accounts.load("tplus-account")

# Load the T+ public key whose inventory is being settled.
user_id = UserManager().load("alice").public_key

nonce = vault.getDepositNonce(eth_account)

order = Order(
    tokenOut="0x62622E77D1349Face943C6e7D5c01C61465FE1dc",
    amountOut=convert("1 ether", int),
    tokenIn="0x58372ab62269A52fA636aD7F200d93999595DCAF",
    amountIn=convert("1 ether", int),
    userId=user_id,
    nonce=nonce,
    validUntil=chain.pending_timestamp,
)

signature = eth_account.sign_message(order).encode_rsv()
```

The encoded signature can then be passed to `vault.executeAtomicSettlement`
or to the CE via {py:meth}`tplus.client.clearingengine.settlement.SettlementClient.init_settlement`.

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

In a local network the contract wrappers will lazily deploy a development
copy if no deployment is registered:

```{code-block} python
from tplus.evm.contracts import DepositVault

vault = DepositVault.deploy_dev()
```

This is intended for tests; production deployments are managed via the
`tplus-contracts` repo.
