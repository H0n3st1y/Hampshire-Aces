# Optional RL experiment (owned by Claude)

Status: **not started — protocol only.** No training code, results, or model
artifacts exist yet. The demo's strategy is the fixed rule in
`backend/agents/strategy.py` (`policy_mode: "rule_based"`).

Per TEAM_HANDOFF.md / CLAUDE_PLANNER.md this begins only after the integrated
core works (hour 24) and must stop at hour 30. It must wrap Codex's research
simulation adapter (due hour 18) rather than re-implementing balances, costs,
or the risk gate.

## Planned design (subject to the adapter's actual interface)

- **Policy:** tabular Q-learning over a small discretized state. Hardcoded rules
  or prompt chains do not count as RL.
- **State (decision-time only):** sentiment label from `sentiment.analyze`
  (positive/negative/neutral/mixed/insufficient), volatility bucket from
  Codex's `daily_volatility`, focus-position weight bucket, cash bucket.
- **Actions:** hold / increase one step / reduce one step, mapped to the same
  `proposal` shape the fixed rule returns. The gate stays authoritative; a
  blocked action executes nothing and is counted.
- **Reward:** next-step simulated portfolio change after costs (costs counted
  once, by the adapter), minus a documented downside penalty on negative
  next-step returns. The penalty shapes behaviour; it does not bound losses.
- **Data:** many generated synthetic sequences from the adapter. Train seeds
  and held-out evaluation seeds are fixed in advance and never tuned on.
- **Comparison:** fixed rule vs. learned policy vs. always-hold, identical
  starting portfolio, gate, execution, and costs.
- **Reported metrics:** total return, maximum drawdown, turnover, blocked
  proposals, per-seed range (not just the best run), configuration, and any
  negative result.
- **Artifact:** a small JSON Q-table loadable by `strategy.propose` without
  training dependencies. `policy_mode: "rl"` is returned only when that real
  artifact produced the proposal.

Synthetic results would demonstrate learning mechanics only, not real-market
performance.

## What Claude needs from Codex's simulation adapter

1. `reset(seed) -> observation` producing the same policy-visible observation
   shape as production (no future fields).
2. `step(proposal) -> (next_observation, result)` where `result` includes gate
   status/rule IDs, portfolio value before/after in cents, and execution cost
   in cents, using the production gate, cost, and balance functions.
3. A generator for multiple synthetic price/headline sequences keyed by seed.
4. A documented episode length and transaction-cost assumption.
