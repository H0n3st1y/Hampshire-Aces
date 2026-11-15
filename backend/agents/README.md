# backend/agents (owned by Claude)

Pure-Python modules that Codex's backend imports and calls in-process. No HTTP
server, no file reads, no network unless model mode is explicitly enabled.
Standard library only by default.

```python
from backend.agents import sentiment, strategy, coach

s = sentiment.analyze(observation)
p = strategy.propose(observation, s)
# ... Codex validates p, applies its independent gate, computes outcomes ...
lesson = coach.explain(decision_facts)
```

Run from the repository root:

```
python -m unittest discover -s backend/agents/tests -t .
python -m backend.agents.examples
```

## Input shapes (contract v1: see contracts/agents-v1.md; local fixtures also accepted)

All parsing goes through `_common.normalize_observation`, the single place to
adapt once Codex freezes `backend/contracts.py`. Missing fields degrade to
hold / "insufficient" with warnings; nothing raises.

**observation** (decision-time only):

| Field | Used for |
|---|---|
| `scenario_id`, `as_of` | passthrough context |
| `headlines: [{id, text, published_at, fixture_tone?}]` | sentiment; `fixture_tone` ∈ positive/negative/neutral overrides keyword rules |
| `fixture_sentiment: {headline_id: tone}` (optional) | alternative place for scripted labels |
| `portfolio: {cash_cents, positions[...], total_value_cents}` | held quantity, decision-time price |
| `price_history: {SYMBOL: [{date, price_cents}]}` (optional) | price fallback if no position |
| `metrics: {daily_volatility, position_weight_before, lookback_days}` | context text only; never recalculated |
| `focus_symbol` | instrument the strategy may trade |
| `permitted: {symbols: [...], actions: [...]}` | hold if buy/sell or symbol not permitted |
| `action_settings: {step_value_cents?, step_fraction?, high_volatility_threshold?}` | sizing; defaults 5% of total value and 0.03 |
| `evidence: [{id, kind, label, description}]` | strategy cites `price_series` / `portfolio` IDs |

Any key named `outcome`, `next_step`, `next_price(_cents)`, `future_prices`,
etc. is stripped before use and reported in `warnings`.

**decision_facts** for the coach: `action`, `proposal`, `gate {status,
rule_ids, explanation, max_position_weight}`, `metrics` (incl.
`position_weight_proposed`), `comparison {end_value_if_executed_cents,
end_value_if_hold_cents, execution_cost_cents}`, optional `sentiment_label`.

## Outputs

| Function | Keys |
|---|---|
| `sentiment.analyze` | `specialist{role:"sentiment",summary,evidence_ids,limitations}`, `analysis_mode` (`fixture`/`model`), `warnings`, `sentiment_label`, `headline_assessments[{headline_id,tone,source}]` |
| `strategy.propose` | `proposal{type,symbol,quantity,reason}`, `specialist{role:"strategy",...}`, `policy_mode` (`rl` or `rule_based`), `warnings` |
| `coach.explain` | `lesson{concept,explanation,question,choices[{id,text}],correct_choice_id,feedback}`, `explanation_mode` (`template`), `warnings` |

Evidence IDs are always a subset of supplied headline IDs and observation
evidence IDs. Hold is always `{type:"hold", symbol:null, quantity:0}`.

## Behaviour

- **Sentiment:** per-headline tone from fixture labels, else a fixed keyword
  list (labelled `fixture`, with a limitation saying it is not a model).
  Aggregate: none → insufficient; positive and negative → mixed; else the one
  tone present; all neutral → neutral.
- **Strategy (default: trained RL):** uses the artifact in
  `research/artifacts/q_policy_v1.json` via `rl_policy.py` (see research/README.md),
  falling back to the fixed rule with a warning when the artifact or state is
  unusable. `AGENTS_POLICY=rule_based` forces the fixed rule: positive → buy
  `action_quantity`; negative → sell it (≤ held); otherwise hold. Neither
  checks the 20% cap; the gate does.
- **Coach:** picks one concept from the recorded facts — unavailable →
  `missing_data`; blocked by weight/cap → `concentration`; other block →
  `trade_constraints`; mixed sentiment → `conflicting_sentiment`; volatility
  ≥ threshold → `volatility`; hold → `holding`; else `transaction_costs`. It
  quotes the gate's explanation and supplied values, never shows an executed
  value for a blocked/unavailable action, and never reverses the gate.

## Optional model mode (off by default)

`AGENTS_MODEL_ENABLED=1` lets sentiment ask Claude (`claude-opus-5-5`, override
with `AGENTS_MODEL`) for per-headline tones. Requires the `anthropic` package
and SDK-resolvable credentials. Timeout `AGENTS_MODEL_TIMEOUT_SECONDS` (default
8 s, clamped 1–30), one SDK retry, low effort, server-side refusal fallback
enabled. Output must be exactly one tone per supplied headline ID or the module
falls back to `fixture` mode with a warning. Summaries are composed locally
from validated tones, so the model cannot add facts.
