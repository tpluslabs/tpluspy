# AGENTS.md — tpluspy

Guidance for AI agents (Codex and others) working in this package. The fuller,
Claude-oriented guide is [`claude.md`](claude.md); the canonical user docs live in
[`docs/userguides/`](docs/userguides/). Prefer those over reconstructing behaviour
from memory, and cite them.

`tpluspy` is the Python client for the T+ ecosystem: async REST + WebSocket
clients for the OMS/orderbook and clearing engine, Pydantic v2 wire models,
Ed25519 user-key signing, and an optional Ape-based EVM layer.

## First time here? Onboard the user — start here

If a user has just cloned this repo and wants to get started — connect their
wallet/EVM key to T+, find out whether they already have a T+ account and see
what's in it, or create a new frontend-compatible account — run the onboarding
flow. It is defined once, in the skill at
[`.claude/skills/onboard/SKILL.md`](.claude/skills/onboard/SKILL.md), and is
exposed to Codex CLI through the repo skill path
[`.agents/skills/onboard`](.agents/skills/onboard).

**Codex CLI:** run `codex` from this repo, type `/skills`, and choose
`onboard`; or invoke it directly with `$onboard onboard me to T+`. The older
[`prompts/onboard.md`](prompts/onboard.md) custom prompt is kept only as a
legacy fallback.

The flow, in short:

1. Ensure `TPLUS_PRIVATE_KEY` (a 0x-prefixed EVM private key) and
   `TPLUS_API_BASE_URL` are in `.env`. If `TPLUS_PRIVATE_KEY` is missing, ask the
   user to add it — it's the wallet key the T+ frontend uses; the T+ identity is
   derived from it and the key is never broadcast.
2. Run `python .agents/skills/onboard/scripts/onboard.py` (pass `--env-file` if
   `.env` isn't in the cwd). It derives the identity, looks it up via
   `POST /multisig/signers`, and prints a JSON result after
   `=== ONBOARD_RESULT_JSON ===`. Branch on `status`.
3. `existing_account` → summarize the account state in the JSON and use
   [`.claude/skills/onboard/reference/tpluspy-primer.md`](.claude/skills/onboard/reference/tpluspy-primer.md)
   to help the user build scripts. `no_account` → guide
   `python .agents/skills/onboard/scripts/create_account.py` (preview, then
   `--execute`); creating an account needs USDC on Arbitrum and an allow-listed
   depositor. See `SKILL.md` for the full branch logic and prerequisites.

Onboarding deps: `pip install eth-account eth-keys` (add `web3` to create an
account). These are **not** part of the tpluspy core install.

## Secret handling

- Never read, print, echo, or commit `TPLUS_PRIVATE_KEY` or any derived private
  key. The scripts consume `.env` themselves; confirm presence only, never values.
- Public keys (T+ account id, secp signer) and addresses are safe to show.
- Secrets live in `.env` (gitignored); non-credential config may have defaults.

## Hard rules for this package

- **The `[evm]` extra is load-bearing.** Core install ships only the httpx
  clients, Pydantic models, and Ed25519 signing. `ape`/`eth-ape`/`hexbytes` are
  not installed. Never import `ape`/`hexbytes` at module top-level outside
  `tplus/evm/`. Anything touching vaults/registry/deposits needs
  `pip install "tpluspy[evm]"`.
- **T+ has its own signing scheme.** Off-chain requests are Ed25519 over compact
  JSON via `User.sign()`; on-chain payloads use a T+-specific structured message.
  Do **not** use generic Ethereum tooling (`eth_account.sign_typed_data`, etc.)
  for T+ flows. The one exception is the onboarding key derivation, which uses
  `eth_account` personal-sign only to reproduce the frontend's wallet-login
  signature — never as a T+ request signature.
- **Async-first, Pydantic v2, Python 3.10+.** Raise the specific exception from
  `tplus.exceptions`; don't swallow into bare `Exception`.
- **Don't run the test suite in agent sessions** unless asked; the user runs tests.

## The `tplus` CLI — surface it to the user

tpluspy ships a `tplus` CLI; for many goals it's faster than a script. The `tplus`
command exists after `pip install -e .` (otherwise `python -m tplus._cli ...`); it
honors `TPLUS_API_BASE_URL` as the single URL (orderbook = that host; market-data
derived `oms`->`mds`) and auths from its own keystore:

```bash
export TPLUS_API_BASE_URL=https://oms.tplus.cx   # the only URL the CLI needs (per-service vars override)
python .agents/skills/onboard/scripts/onboard.py --register-cli-account   # import key (encrypted; never printed)
export TPLUS_ACCOUNT=onboard
```

- No account needed: `tplus params list`, `tplus markets depth <asset>`, `tplus markets klines <asset>`, `tplus --help`.
- As the account: `tplus markets list`, `tplus balance`, `tplus orders list`, `tplus trades list`, `tplus stream user-trades`.

Full cheatsheet: `.agents/skills/onboard/reference/tpluspy-primer.md`
(same file as `.claude/skills/onboard/reference/tpluspy-primer.md`).

## Anchor objects

```python
from tplus.utils.user import User, load_user
from tplus.client import OrderBookClient, MarketDataClient, ClearingEngineClient
```

`OrderBookClient(base_url=…, default_user=user)` for orders/inventory/positions;
`MarketDataClient(base_url=…)` for public data (no auth); `ClearingEngineClient`
for deposits/withdrawals/settlements. All T+ URLs derive from
`TPLUS_API_BASE_URL`. See `claude.md` and `docs/userguides/` for the full surface.
