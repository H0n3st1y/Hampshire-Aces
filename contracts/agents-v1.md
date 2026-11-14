# Internal specialist interface v1

Claude owns `backend/agents/` and `research/`. Codex owns `backend/contracts.py`, the public API, fixtures, arithmetic, gate, orchestration, backend dependencies, and research simulation adapter. The frontend teammate owns `frontend/`. Neither agents nor research may bypass the gate or change live backend balances.

`backend/contracts.py` is the executable schema reference. All records forbid extra fields, reject type coercion, and reject NaN/infinity. Money is integer USD cents; shares are nonnegative integers; ratios are fractions. Agent functions receive ordinary copied JSON-compatible dictionaries and return either a matching dictionary or the corresponding Pydantic model. They may be synchronous or asynchronous.

## Callables and loading

```python
# backend/agents/sentiment.py
def analyze(observation: dict) -> dict: ...  # SentimentResult

# backend/agents/strategy.py
def propose(observation: dict, sentiment_result: dict) -> dict: ...  # StrategyResult

# backend/agents/coach.py
def explain(decision_facts: dict) -> dict: ...  # CoachResult
```

The backend imports `backend.agents.sentiment`, `backend.agents.strategy`, and `backend.agents.coach`. Importing must not start a server, train a model, or require optional research dependencies. Request runtime dependency additions in `docs/CLAUDE_STATUS.md`; Codex alone edits the shared backend dependency manifest and lockfile. Keep optional training dependencies in `research/`.

Default `AGENT_MODE=auto` attempts the installed modules. `AGENT_MODE=offline` bypasses them for an explicit dependable emergency demo. Each call runs in a separate process with a default three-second bound, including module import; timed-out workers are terminated. The maximum result size is 64 KiB. Provider calls should also have their own bounded network timeouts. Missing modules, timeout, invalid schema, wrong role, unresolved evidence references, or oversized output invoke the backend's labeled fallback. Do not depend on process memory persisting across calls.

## Observation

Both sentiment and strategy receive this exact decision-time `Observation` shape:

```text
schema_version: "1"
scenario_id: string
synthetic: true
as_of: ISO-8601 UTC string
headlines: [{id: string, text: string, published_at: UTC string}]
historical_prices_cents: [integer | null, ...]
portfolio: Portfolio
metrics: Metrics
evidence: [Evidence, ...]
permitted: {
  symbols: [string, ...],
  actions: ["hold", "buy", "sell"],
  action_quantity: positive integer,
  max_position_weight: 0.20,
  transaction_cost_cents: 100
}
```

`Portfolio`, `Metrics`, and `Evidence` use the public API types in `api-v1.md`. The pre-proposal metrics always have `position_weight_proposed: null`. `position_weight_before` refers to the permitted scenario instrument. Volatility is the backend's unannualized sample standard deviation of daily simple returns, requiring at least three valid daily prices. Six prices give `lookback_days: 5`. Missing required history yields a null statistic and a warning/limitation rather than zero.

Evidence includes every decision-time headline and backend records `prices:SYMBOL` and `portfolio:initial`. Use only IDs present in the observation. Specialists should state uncertainty and missing-data limitations; they must not invent URLs, prices, headlines, evidence IDs, or live-provider claims.

Observations deliberately omit the canonical fixture, next-step prices, comparison outcomes, a reward, and a future return. Do not open `contracts/scenarios.json` or otherwise read hidden outcome data from agent code. The backend supplies copied observations so mutation cannot affect execution, but agents should treat inputs as read-only. This separation prevents routine data leakage; it is a cooperative module boundary, not an operating-system security boundary against malicious code.

## SentimentResult

```json
{
  "sentiment_label": "neutral",
  "headline_assessments": [
    {"headline_id": "beta:routine", "tone": "neutral", "source": "keyword_rules"},
    {"headline_id": "beta:schedule", "tone": "neutral", "source": "keyword_rules"}
  ],
  "specialist": {
    "role": "sentiment",
    "summary": "The synthetic headlines do not give a clear directional signal.",
    "evidence_ids": ["beta:routine", "beta:schedule"],
    "limitations": ["These fictional headlines cannot predict the next price."]
  },
  "analysis_mode": "fixture",
  "warnings": []
}
```

Allowed `sentiment_label` values: `positive`, `negative`, `neutral`, `mixed`, `insufficient`. Every headline assessment has a supplied `headline_id`, a `tone` of `positive`, `negative`, or `neutral`, and a `source` of `fixture_label`, `keyword_rules`, or `model`. The specialist role must be `sentiment`. `analysis_mode` is `fixture` for scripted/fixture/keyword analysis and `model` only when a real model supplied the analysis. Return accurate labels when falling back from a provider. No model call is required for the core demo.

Assess every supplied headline exactly once; no headline may be omitted or duplicated. Backend fallback sentiment is the only emergency placeholder exempt from this module-output requirement.

## StrategyResult

Strategy receives the validated sentiment result as its second dictionary argument:

```json
{
  "proposal": {
    "type": "hold",
    "symbol": null,
    "quantity": 0,
    "reason": "The neutral synthetic evidence does not justify changing exposure."
  },
  "specialist": {
    "role": "strategy",
    "summary": "Propose holding while the evidence remains inconclusive.",
    "evidence_ids": ["beta:routine", "prices:BETA", "portfolio:initial"],
    "limitations": ["The independent risk gate decides whether a proposal is permitted."]
  },
  "policy_mode": "rule_based",
  "warnings": []
}
```

The role must be `strategy`. Proposal type is `hold`, `buy`, or `sell`. Hold requires quantity 0 and symbol null; buy/sell requires a positive whole-share quantity and one permitted symbol. Booleans, fractional values, negative quantities, NaN, and infinity are invalid. Do not execute trades, secretly resize proposals, claim a proposal has been approved, calculate replacement balances, or override the gate.

`policy_mode` is `rule_based` for fixed heuristics and the backend's explicit user choices. `rl` is reserved for an actually trained, integrated artifact. Backend `increase`, `reduce`, and `hold` selections construct explicit proposals without calling this function; the `strategy` selection uses this function. No competing RL implementation is supplied by Codex.

## DecisionFacts and CoachResult

After validation, gating, portfolio accounting, and outcome calculation, the coach receives `CoachFacts`: `DecisionFacts` (the full public evaluation object except `lesson` and `explanation_mode`) plus internal-only `action` and validated `sentiment_label`. It includes verified proposal, gate, specialists, evidence, metrics, before/after portfolios, comparison, warnings, modes, IDs, timestamps, and `synthetic: true`. The coach may see next-step comparison outcomes only at this post-decision stage.

Initial integration clarification: `action` and `sentiment_label` are additive coach-only context consumed by Claude's existing coach. They are never added to the public response or strategy observation. Existing coaches that ignore them remain compatible. This clarification preserves the public v1 contract.

Return:

```json
{
  "lesson": {
    "concept": "Concentration and independent limits",
    "explanation": "The proposed increase was blocked because its post-fee position weight would exceed the illustrative 20% limit. The simulated portfolio was unchanged.",
    "question": "What happens when the independent gate blocks a proposal?",
    "choices": [
      {"id": "unchanged", "text": "Balances stay unchanged and no trade cost is charged."},
      {"id": "resize", "text": "The simulator silently buys a smaller quantity."}
    ],
    "correct_choice_id": "unchanged",
    "feedback": "A blocked proposal is not executed or resized. Holding can still gain or lose value at the next synthetic price."
  },
  "explanation_mode": "template",
  "warnings": []
}
```

This sample lesson applies to a blocked increase only. Ground actual explanations in the supplied facts. `explanation_mode` is `template` for fixed text and `model` only for a real model-generated explanation. Choices require two to six objects with distinct IDs; `correct_choice_id` must match one. The coach cannot replace recorded decisions or balances. Never describe an unavailable/blocked proposal as an executed trade or a risk rule as a guarantee against loss.

## Independent gate and fallback behavior

The deterministic gate owns the final decision for every proposal source. Its stable blocking/unavailable rule IDs are:

| Rule ID | Meaning |
|---|---|
| `INVALID_PROPOSAL` | Invalid action shape, types, or quantities |
| `SYMBOL_NOT_ALLOWED` | Instrument is outside the permitted scenario universe |
| `MARKET_DATA_INVALID` | A required price/market input is invalid |
| `MARKET_DATA_MISSING` | Required observations are absent or insufficient |
| `CASH_INSUFFICIENT` | Buy plus the fixed fee exceeds cash |
| `HOLDINGS_INSUFFICIENT` | Sell quantity exceeds holdings |
| `POSITION_LIMIT` | Resulting position exceeds 20% of the post-fee portfolio |

Allowed trades use `ALL_CHECKS_PASSED`; allowed holds use `HOLD`. No borrowing, shorting, fractional shares, hidden resizing, or fee-free permitted trades. Hold costs zero. Missing history yields unavailable and unchanged balances even when the proposal is hold.

Fallbacks live outside Claude's directories: labeled neutral sentiment, zero-quantity hold policy, and a grounded template lesson. They are emergency continuity behavior, not a competing strategy or trained RL model. Validation or provider failures must be visible in warnings, with `fixture`/`rule_based`/`template` mode labels as appropriate.

## Research reuse

Codex supplies `backend.simulation.simulate(fixture, proposal)` as the callable adapter for optional research. It reuses production costs, arithmetic, and the gate; future prices are used only after the gate. See the actual function signature/docstring before consuming it, and keep private outcomes in the environment's post-action reward path. Ordinary backend startup must not import research packages, train a policy, or require model artifacts. Request adapter changes through `docs/CLAUDE_STATUS.md`; do not duplicate the execution or risk rules.
