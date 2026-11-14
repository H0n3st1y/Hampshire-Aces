# Shared agreement: two backend assistants and a frontend teammate

Read this alongside your assigned planner. The user owns backend work using Codex and Claude; a separate human teammate owns the frontend. This revised agreement supersedes earlier assignments giving Claude frontend work. Hours are elapsed from project start; this revision does not restart the 48-hour clock. This is a proposed implementation contract, not a claim that software has been built.

**Finish line**

Deliver a working educational web demo: select one of three clearly synthetic market scenarios, inspect specialist evidence, compare a simulated action with holding, see an independent risk decision, and answer a learning question. Start each scenario with a fictional $10,000 portfolio. Use daily price observations and fictional assets. No login, brokerage, live feeds, or automatic model retraining.

The default implementation is a TypeScript web frontend in frontend/ and a Python HTTP backend in backend/. Choose familiar tooling inside those boundaries. Each application owns its dependencies and lockfile; do not introduce a shared root dependency manifest. If existing application code appears, inspect it before changing the stack. There is no requirement to buy services or obtain API keys for the core demo.

**Who owns what**

| Area | Owner |
|---|---|
| backend/ except backend/agents/; API, shared schemas/dependencies, simulation, risk calculations, core tests | Codex |
| backend/agents/ including its tests; sentiment, strategy proposals, grounded coach | Claude |
| research/, optional RL training and evaluation artifacts | Claude |
| contracts/, canonical scenario fixtures, root README and launch instructions | Codex |
| frontend/, its dependencies, UI tests and local UI mock adapter | Frontend teammate |
| docs/DEMO_SCRIPT.md, docs/USER_TEST.md, UI copy and presentation | User + frontend teammate |
| docs/CODEX_STATUS.md | Codex |
| docs/CLAUDE_STATUS.md | Claude |
| Event rubric, product decisions, beginner walkthroughs, actual submission | User |

Both assistants may read all files. Edit only owned paths. Do not overwrite, revert, or clean the other assistant's or teammate's changes. Codex coordinates backend integration and provides the frontend API; neither assistant builds the frontend. Record cross-boundary issues and proposed fixes in your status file for the owning assistant. Use separate checkouts/branches if available, or enforce directory boundaries in a shared folder. Never switch a shared checkout's branch while another contributor uses it. Codex alone edits shared backend dependency manifests and lockfiles; Claude requests runtime additions in docs/CLAUDE_STATUS.md. Optional training dependencies may remain isolated in research/.

These are two user-operated assistants. They do not automatically receive each other's chat messages. Use shared status files when both have workspace access; otherwise the user transfers the contract bundle and status updates at checkpoints. Never claim that the other assistant has completed work without inspecting its delivered files or status.

**Contract v1: freeze by hour 2**

Codex creates contracts/api-v1.md, contracts/scenarios.json, and contracts/examples/ with complete responses during the first two hours. Give these to the frontend teammate. Claude builds the internal modules described below. Do not change names or units after the freeze without a documented migration implemented by affected consumers.

**Internal backend boundary: freeze by hour 2**

Codex owns backend/contracts.py and contracts/agents-v1.md defining these callable Python interfaces. Claude owns their implementations inside backend/agents/:

- sentiment.analyze(observation): sentiment specialist record, analysis_mode, and warnings.
- strategy.propose(observation, sentiment_result): proposal, strategy specialist record, policy_mode, and warnings.
- coach.explain(decision_facts): lesson, explanation_mode, and warnings.

Observations contain decision-time headlines/evidence IDs, historical prices, holdings, Codex-calculated metrics, and permitted instruments/action settings. They exclude next-step outcomes and full fixtures containing future values. Modules receive copies or immutable records and must not mutate holdings or read hidden future data from fixture files.

Codex assembles observations, invokes sentiment/strategy, validates outputs, applies its independent gate, computes outcomes, and invokes the coach with verified facts. Explicit hold/increase/reduce user choices are constructed by Codex; Claude's policy handles the strategy choice. Claude does not approve or execute trades, change risk limits, recalculate balances, or edit public endpoints. The coach explains recorded results and cannot reverse them.

Codex enforces timeouts, response validation, and a labeled neutral/hold/template emergency fallback in its own code, or an unavailable result when required data is missing. Claude provides bounded provider calls and accurate mode labels. By hour 18 Codex supplies a callable research simulation adapter so Claude reuses the same cost, arithmetic, and gate functions for training/evaluation. Optional training dependencies must not be imported during ordinary backend startup.

Two required endpoints:

- GET /api/scenarios returns {schema_version: "1", scenarios: [...]}.
- POST /api/evaluate accepts {schema_version: "1", scenario_id: string, action: "strategy" | "hold" | "increase" | "reduce"} and returns the evaluated comparison below.

A scenario contains id, title, as_of (ISO-8601 UTC timestamp), synthetic: true, summary, headlines [{id, text, published_at}], and initial_portfolio. Canonical fixtures also contain historical price sequences and a separate next-step outcome used only by the execution simulator. The analysis/policy input must exclude that future outcome.

A portfolio contains cash_cents, positions [{symbol, name, quantity, price_cents, value_cents}], and total_value_cents. Use integer share quantities and integer USD cents. Calculate balances and rounding in the backend. All ratio fields use fractions: 0.20 means 20%. Volatility is the sample standard deviation of the supplied daily simple returns, unannualized; document the lookback and require enough observations. A missing statistic is null with a limitation, never silently zero.

An evaluation response contains:

- schema_version, scenario_id, evaluation_id, synthetic: true, as_of.
- analysis_mode: "model" or "fixture"; policy_mode: "rule_based" or "rl"; explanation_mode: "template" or "model". These are backend facts that the frontend displays accurately.
- specialists: [{role: "sentiment" | "risk" | "strategy", summary, evidence_ids: string[], limitations: string[]}]. Evidence IDs refer to supplied headlines or backend-defined price/portfolio evidence records included in the response; they are not invented URLs.
- evidence: [{id, kind: "headline" | "price_series" | "portfolio", label, description}].
- metrics: {daily_volatility: number | null, position_weight_before: number, position_weight_proposed: number | null, lookback_days: number}.
- proposal: {type: "hold" | "buy" | "sell", symbol: string | null, quantity: integer, reason: string}. Hold uses quantity 0 and symbol null.
- gate: {status: "allowed" | "blocked" | "unavailable", rule_ids: string[], explanation: string, max_position_weight: 0.20}.
- portfolio_before and portfolio_after_action using the portfolio schema above. Blocked/unavailable actions leave the latter equal to the former.
- comparison: {end_value_if_executed_cents: integer | null, end_value_if_hold_cents: integer, execution_cost_cents: integer, explanation: string}. A blocked action has no executed outcome; show null rather than an apparently completed trade. Mark-to-market hold outcome can still differ from the starting portfolio.
- lesson: {concept: string, explanation: string, question: string, choices: [{id, text}], correct_choice_id: string, feedback: string}.
- warnings: string[].

Unknown scenario/action or malformed input returns HTTP 400 with {error: {code, message}}. An unexpected server failure returns a generic HTTP 500 error without secrets. Missing market data in a known scenario returns a valid evaluation with gate.status "unavailable" and an explanation. Codex documents the exact nullable fields in the canonical contract before integration.

This is a stateless, one-step comparison tool. Every evaluation begins at the scenario's initial portfolio. Clicking twice must not apply the action twice. The frontend must say comparisons restart from the same portfolio; continuous multi-step portfolio persistence is deferred. If requests complete out of order, display only the response for the latest selection.

**Demonstration rules**

Single-stock positions may not exceed 20% of post-trade portfolio value after costs. This is an illustrative simulator setting, not personalized investment advice. No borrowing, shorting, fractional shares, or hidden resizing of blocked actions. Hold is valid. Validate positive finite prices and sufficient cash/holdings. Risk limits constrain actions, not all future losses.

Use a documented fixed transaction-cost assumption shared by all policies. Canonical fixtures must include a proposed action that is blocked and an alternative that is allowed. Codex supplies hand-checked expected results. Future price outcomes must be inaccessible to sentiment/strategy analysis.

Use three scenarios: positive news plus rising volatility and concentration; quiet neutral conditions; conflicting headlines. Fixture-based sentiment is acceptable for the dependable demo if labeled as such. Do not call a scripted fixture a live model analysis or a rule-based policy trained RL.

**Integration checkpoints**

| Elapsed time | Joint checkpoint |
|---|---|
| Hour 2 | Public API examples and internal agent schemas ready; frontend teammate receives API bundle |
| Hour 8 | Codex calls Claude's initial modules; teammate's frontend reads the scenario endpoint |
| Hour 14 | One real frontend → backend → explanation → learning-question flow works |
| Hour 18 | Three scenarios and all four action choices are connected |
| Hours 18–24 | Rest/buffer; save a known working version |
| Hour 24 | Claude attempts optional RL if core works; Codex hardens backend and supports frontend integration |
| Hour 30 | RL cutoff; freeze features and contract |
| Hour 36 | Two beginner walkthroughs complete; critical issues fixed |
| Hour 42 | Demo rehearsal and backup recording ready |
| Hours 42–48 | Final verification, submission packaging, and buffer |

Checkpoint outputs: updated owned status file listing completed work, files changed, commands to run, checks performed, remaining blockers, and any requested change for the other assistant. Report facts rather than guessed completion percentages.

If the core flow is behind at hour 14, cut optional model calls and RL before cutting the risk gate or clear explanation. If the event requires trained RL, the user should flag it immediately so the scope can be adjusted.
