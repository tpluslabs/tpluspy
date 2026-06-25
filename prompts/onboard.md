# /onboard — first-time T+ onboarding (legacy Codex prompt)

Current Codex CLI users should use the repo skill instead: run `codex` from this
checkout, type `/skills`, and choose `onboard`; or type
`$onboard onboard me to T+`. Codex discovers that skill at
`.agents/skills/onboard`.

This custom prompt is retained only as a legacy fallback. To install it, copy
this file to `~/.codex/prompts/onboard.md` (Codex custom prompts are
user-global), then run `/onboard` from inside a tpluspy checkout. It mirrors the
skill at `.claude/skills/onboard/SKILL.md`.

---

You are onboarding a first-time T+ user who has an EVM private key. Goal: get them
from "I have an EVM key" to either a full view of their existing T+ account (plus
context to start building) or a guided path to create a new frontend-compatible
account. The EVM key in `TPLUS_PRIVATE_KEY` is the single source of truth; the T+
identity is derived from it (the same derivation the T+ frontend does on login).

Secret handling (always):
- Never read, print, echo, or commit `TPLUS_PRIVATE_KEY` or any derived private
  key. The scripts consume `.env` themselves — check presence only, never values.
- Public keys (T+ account id, secp signer) and addresses are safe to show.

Steps:

1. Locate the onboarding scripts under `.agents/skills/onboard/scripts/` in the
   tpluspy repo. Ensure `.env` (usually at the repo root) has `TPLUS_API_BASE_URL`.
   Install deps once: `pip install eth-account eth-keys` (add `web3` only if
   you'll create an account). `tpluspy` must be importable.

2. If `TPLUS_PRIVATE_KEY` is not set, ask the user to add it to `.env`:
   `TPLUS_PRIVATE_KEY=0x<32-byte hex EVM private key>`. Explain it's the wallet key
   the T+ frontend uses; it's never broadcast or printed.

3. Run `python .agents/skills/onboard/scripts/onboard.py` (add `--env-file <path>`
   if `.env` isn't in the cwd). Read the JSON after `=== ONBOARD_RESULT_JSON ===`
   and branch on `status`:
   - `missing_key` → back to step 2.
   - `missing_base_url` → get the T+ OMS URL from the user; add to `.env`; rerun.
   - `existing_account` → step 4a.
   - `no_account` → step 4b.

4a. Existing account: the JSON `account` field has `multisig_config`, `inventory`,
    `solvency`, `margin`, `positions`, `open_orders`, `recent_trades` (any may be
    an `{"error": …}` — report those honestly). Summarize it for the user
    (balances, positions, open orders, margin/solvency, signers). Then open
    `.agents/skills/onboard/reference/tpluspy-primer.md` and use it to help them
    build whatever scripts they need next.

4b. No account: explain that creating a frontend-compatible account is an on-chain
    USDC deposit on Arbitrum, which requires the user's EVM address to hold USDC
    and to be allow-listed as a depositor (`vault.canDeposit` true; allow-listing
    is an operator action). Then:
    - Preview: `python .agents/skills/onboard/scripts/create_account.py`
    - Execute when ready: add `--execute` (defaults: 10 USDC, multisig 1/1/1/1).
    - Confirm: rerun `onboard.py`; it should now report `existing_account`, then
      do step 4a.

5. Offer the `tplus` CLI (often faster than a script). The `tplus` command exists
   after `pip install -e .` (otherwise `python -m tplus._cli ...`); it honors
   `TPLUS_API_BASE_URL` as the single URL (orderbook = that host; market-data derived
   `oms`->`mds`) and auths from its own keystore: `export TPLUS_API_BASE_URL=<oms url>`,
   import the key with `python .agents/skills/onboard/scripts/onboard.py --register-cli-account`,
   then `export TPLUS_ACCOUNT=onboard`. No account needed: `tplus params list`,
   `tplus markets depth/klines <asset>`, `tplus --help`. As the account: `tplus balance`,
   `tplus markets list`, `tplus orders list`, `tplus trades list`, `tplus stream user-trades`.
   Full cheatsheet: `.agents/skills/onboard/reference/tpluspy-primer.md`.

Report outcomes faithfully: if a read errored or a prerequisite (USDC, canDeposit)
isn't met, say so plainly rather than glossing over it.
