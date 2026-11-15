# Claude status

Last updated: 2026-11-14. Owner: Claude. Scope: `backend/agents/`,
`research/`, this file. No frontend work was done or touched.

The user confirmed **trained RL is required** and chose **RL as the demo
strategy mode** (2026-11-14). `strategy.propose` now uses the trained artifact
by default; `AGENTS_POLICY=rule_based` still forces the fixed rule. Details and
full results are in `research/README.md`.

## Completed

- **Agents (contract v1):** `sentiment.analyze`, `strategy.propose`,
  `coach.explain` run against Codex's frozen `Observation` / `CoachFacts`.
- **Contract alignment (Codex requests):**
  - strategy now uses `permitted.action_quantity` exactly and reads
    `historical_prices_cents`;
  - the coach's allowed-hold lesson no longer says "no executed outcome";
  - a proposed weight that rounds to the 20.0% cap now reads "just over 20.0%
    (the fixed trading fee tips it over)".
- **RL:** tabular Q-learning trained through Codex's production
  `backend.simulation.simulate` adapter. It ran 5 training seeds and was
  evaluated on 400 held-out episodes against the fixed rule and always-hold.
  The artifact `research/artifacts/q_policy_v1.json` (seed 0, pre-declared) is
  loaded by `strategy.propose` by default (unless `AGENTS_POLICY=rule_based`). It returns
  `policy_mode: "rl"` only when that artifact produced the proposal; a missing
  or invalid artifact, missing `action_quantity`, or a state with fewer than 20
  training visits falls back to the rule with a warning.
- **RL result (honest):** lower return than the fixed rule (mean 0.04–0.10%
  vs 0.19%), but about half the drawdown (0.22–0.30% vs 0.51%) and 3–14× fewer
  blocked proposals. It mostly de-risks into cash (median 0%).

## Files changed this round

```
backend/agents/_common.py        (contract field names, action_quantity)
backend/agents/strategy.py       (action_quantity sizing, RL inference path)
backend/agents/coach.py          (hold outcome fix, cap-boundary wording)
backend/agents/rl_policy.py      (new: shared state features + artifact loader)
backend/agents/tests/test_strategy.py   (updated RL/contract tests)
backend/agents/tests/test_rl_policy.py  (new)
research/rl/__init__.py, research/rl/env.py, research/rl/train.py   (new)
research/artifacts/q_policy_v1.json, research/artifacts/runs/*.json (new)
research/results/rl_eval_v1.json (new)
research/README.md, docs/CLAUDE_STATUS.md
```

## Commands (repository root)

```
backend/.venv/Scripts/python -m pytest backend/tests backend/agents/tests -q
backend/.venv/Scripts/python -m research.rl.train
```

## Checks performed

- Combined suite: **162 passed** (Codex's 106 plus Claude's 56), 1 existing
  Starlette deprecation warning.
- Full training and evaluation completed in 318 s; numbers in
  `research/results/rl_eval_v1.json`.
- Through `TestClient(backend.main.app)` with Codex's worker processes, all
  three canonical scenarios returned no fallback warnings:
  - `AGENTS_POLICY=rl` → `policy_mode: "rl"`;
  - `rule_based` → unchanged behaviour (momentum buy 5 blocked by
    POSITION_LIMIT).
- Not performed: any real model call (model mode remains off); the RL artifact
  was not checked against the running server on port 8000, which was started
  with `rule_based`.

## Requests / notes for Codex

1. **Action needed: relaunch with RL.** The user chose RL for the demo. Your
   launch instructions (`docs/CODEX_STATUS.md`, `README.md`) set
   `AGENTS_POLICY=rule_based`, which overrides the new RL default. Please change
   them to `AGENTS_POLICY=rl` (or leave it unset) and restart the server on port
   8000. Claude did not stop your running instance (PID 24716, still
   `rule_based` at this update). Also update the README sentence "No RL model
   is trained by this backend" to point to Claude's artifact. Your tests are
   unaffected (they pin `rule_based` or run offline). With RL, momentum
   "strategy" holds; the blocked example now comes from the learner's
   "increase" choice.
2. **Artifact path:** `strategy.propose` reads
   `research/artifacts/q_policy_v1.json` (override with `AGENTS_RL_ARTIFACT`)
   only in RL mode. It is about 8 KB of JSON, and loading it is well within
   the 3 s bound. Ordinary startup imports no research code.
3. **Release snapshot:** `backend/scripts/snapshot.py` excludes `research/`. If
   RL mode should survive a restore, include
   `research/artifacts/q_policy_v1.json`.
4. **Adapter:** the one-step `simulate` was sufficient; Claude chains steps in
   `research/rl/env.py` and asserts totals against your end values. No adapter
   change is needed.
5. **Optional `anthropic` dependency** is still not needed. If enabled later,
   lower `AGENTS_MODEL_TIMEOUT_SECONDS` below your 3 s agent deadline.

## Remaining

- Codex: relaunch port 8000 with RL (request 1) and include the artifact in the
  release snapshot (request 3).
- User and frontend teammate: in the demo script, show the risk block through
  the "increase" choice on momentum_concentration, and describe the RL policy
  truthfully: trained on synthetic data, lower return but lower drawdown than
  the fixed rule.
- Claude's work is on branch `claude/rl-policy` with a pull request into
  `main`; it is not merged yet.
