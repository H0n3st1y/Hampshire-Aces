# Claude status

Last updated: 2026-11-14. Owner: Claude. Scope per the revised TEAM_HANDOFF.md
and CLAUDE_PLANNER.md: `backend/agents/`, `research/`, this file. No frontend
work is assigned to Claude; none was done or touched.

## Workspace state seen at this update

Only the planning docs existed (TEAM_HANDOFF.md, CLAUDE_PLANNER.md,
CODEX_PLANNER.md, BUILD_PLANNER.md, HACKATHON_48H.md). There was **no**
`contracts/`, `backend/contracts.py`, `contracts/agents-v1.md`, `frontend/`, or
`docs/CODEX_STATUS.md`. The folder is not a git repository. The modules below
therefore use provisional input shapes and Claude-owned local fixtures.

## Completed

- `sentiment.analyze(observation)` — offline fixture/keyword analysis with
  supplied evidence IDs, conflicting/empty handling, optional bounded model
  mode with strict output validation and labelled fallback.
- `strategy.propose(observation, sentiment_result)` — fixed rule,
  `policy_mode: "rule_based"`, whole-share hold/buy/sell, never shorts or
  oversells, does not self-apply the risk gate.
- `coach.explain(decision_facts)` — template lessons (concentration, trade
  constraints, conflicting sentiment, volatility, holding, transaction costs,
  missing data) grounded in supplied gate/comparison facts.
- Future-data guard: outcome/next-step keys are stripped from observations and
  reported in `warnings`.
- Tests: 47 unittest cases covering the checklist in CLAUDE_PLANNER.md hours
  14–18 (empty/conflicting headlines, invalid model JSON, unknown evidence IDs,
  timeout, missing SDK/credentials, missing metrics, allowed/blocked/unavailable
  coaching, no mutation, no file reads, future-field stripping).
- `research/README.md` — RL protocol and adapter requirements only.

## Files

```
backend/agents/__init__.py      backend/agents/README.md
backend/agents/_common.py       backend/agents/provider.py
backend/agents/sentiment.py     backend/agents/strategy.py
backend/agents/coach.py         backend/agents/examples.py
backend/agents/tests/__init__.py
backend/agents/tests/fixtures.py
backend/agents/tests/test_sentiment.py
backend/agents/tests/test_strategy.py
backend/agents/tests/test_coach.py
research/README.md
docs/CLAUDE_STATUS.md
```

## Commands (run from repository root, Python 3.12)

```
python -m unittest discover -s backend/agents/tests -t .
python -m backend.agents.examples
```

## Checks performed

- Unit tests: 47 run, 47 passed (Python 3.12.10, Windows, offline).
- Example script output read by hand for all three local scenarios and the
  sample allowed/blocked/unavailable coach facts.
- Not performed: any real model call (no `anthropic` package installed, model
  mode off by default), integration with Codex's backend (none exists yet),
  checks against canonical fixtures (none exist yet).

## Requests for Codex

1. **Import path.** Modules use relative imports and work as `backend.agents`
   (namespace package today). If you add `backend/__init__.py` or run with
   `backend/` on `sys.path` as `agents`, both work; please say which you use.
2. **Observation shape.** Please map your observation to the fields in
   `backend/agents/README.md`, or tell me your field names and I will adapt
   `_common.normalize_observation` (the single adapter point). Especially:
   - `focus_symbol` (which instrument the strategy may trade),
   - `action_settings.step_value_cents` (strategy sizing; default is 5% of
     `total_value_cents` if absent) — ideally the same step your
     increase/reduce user actions use,
   - `evidence` records for price/portfolio so the strategy can cite them.
3. **Decision facts.** Coach expects `action`, `proposal`, `gate`, `metrics`
   (with `position_weight_proposed`), `comparison`, and optional
   `sentiment_label`. Concentration blocks are recognised from rule IDs
   containing `position`/`concentration`/`weight`/`cap`, or from
   `position_weight_proposed > max_position_weight`; please share your rule IDs.
4. **Extra output keys.** `sentiment_label` and `headline_assessments` (sentiment)
   are internal fields for strategy/coach; strip them before the public
   response if they are not in the API contract.
5. **Fixture mode definition.** `analysis_mode: "fixture"` covers both scripted
   per-headline labels (`fixture_tone`) and the deterministic keyword list. If
   you want canonical fixtures to carry scripted labels, add `fixture_tone` to
   each headline in the observation.
6. **Optional runtime dependency.** Only if the team wants live model
   sentiment: `anthropic` (Python SDK 1.x). Without it everything runs offline.
   Model mode also requires `AGENTS_MODEL_ENABLED=1` and credentials.
7. **Research adapter (hour 18).** Needs listed in `research/README.md`.

## Remaining / blockers

- Adapt to `backend/contracts.py` and `contracts/agents-v1.md` once they exist.
- Re-test against canonical fixtures and Codex's gate rule IDs.
- Coach model mode is not implemented (template only).
- RL not started; waits for working core and the simulation adapter.

## Open question for the user

- Is trained RL required by the event rubric? If not, RL stays optional and
  starts no earlier than hour 24.
