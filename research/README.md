# RL experiment (owned by Claude)

Status: **trained, evaluated, and the default strategy policy** (the user
chose RL for the demo). `strategy.propose` uses the trained artifact unless
`AGENTS_POLICY=rule_based` is set. Results are synthetic and show how the learning works, not
how it would perform in real markets.

## What was built

| File | Purpose |
|---|---|
| `research/rl/env.py` | Multi-step synthetic episodes that wrap Codex's `backend.simulation.simulate` (production fee, gate, accounting) and `backend.service.build_observation` (policy-visible input) |
| `research/rl/train.py` | Tabular Q-learning trainer plus held-out evaluation against the fixed rule and always-hold |
| `backend/agents/rl_policy.py` | Shared state discretization and artifact inference (stdlib only), used by both training and `strategy.propose` |
| `research/artifacts/q_policy_v1.json` | Deployed artifact (run seed 0, chosen before evaluation) |
| `research/artifacts/runs/q_policy_seed{0..4}.json` | All five training runs |
| `research/results/rl_eval_v1.json` | Full evaluation report |

Reproduce from the repository root (about 5 minutes; no extra packages):

```
backend/.venv/Scripts/python -m research.rl.train
backend/.venv/Scripts/python -m research.rl.train --quick   # smoke run, writes nothing
```

## Design

- **Policy:** tabular Q-learning, gamma 0.9, step size max(0.02, 1/visits),
  epsilon 1.0 → 0.05 linearly, 6,000 episodes × 8 steps per run.
- **State (decision-time only):** sentiment label from `sentiment.analyze`,
  daily-volatility bucket (<1.5%, <3%, ≥3%), focus-position weight bucket
  (<5%, <12%, <17%, ≥17%), and a cash bucket (cash under or over 10% of the
  total). 48 states were visited.
- **Actions:** hold / buy `permitted.action_quantity` / sell the same quantity
  (capped at shares held; sell is excluded when nothing is held). Codex's gate
  decides every proposal. A blocked proposal executes nothing and is counted.
- **Reward:** the next-step simulated return after costs, minus 0.5 × any
  negative return, scaled by 100. The $1.00 fee is already in the adapter's end
  value, so costs are counted once. The penalty shapes behaviour; it does not
  bound losses.
- **Synthetic generator:** each episode gets a daily volatility of 0.8%, 2%,
  or 4%. Each step has a hidden signal s ∈ {+1, 0, −1}, and the next return is
  1.2%·s plus noise. Each of the 2 headlines matches s with probability 0.7.
  The policy sees only the headlines, never s or the next price.
- **Chaining:** the adapter is one-step. Each next step starts from the
  adapter's post-action portfolio marked at the revealed price, and the rebuilt
  total is asserted equal to the adapter's own end value.
- **Protocol:** training runs use seeds 0–4. The 400 evaluation episodes use
  seeds 900,000,000 + i, which no training run touches. Nothing was tuned on
  the evaluation results. All policies were evaluated through `strategy.propose`
  on identical episodes.

## Results (400 held-out episodes × 8 decisions)

| Policy | Mean return | Median | 10th pct | Mean max drawdown | Worst drawdown | Trades / episode | Blocked proposals |
|---|---|---|---|---|---|---|---|
| RL seed 0 (deployed) | 0.063% | 0.000% | −0.380% | 0.217% | 1.78% | 2.65 | 21 / 3200 |
| RL seed 1 | 0.049% | 0.000% | −0.541% | 0.273% | 2.69% | 3.59 | 71 / 3200 |
| RL seed 2 | 0.044% | 0.000% | −0.466% | 0.295% | 3.33% | 2.81 | 97 / 3200 |
| RL seed 3 | 0.086% | 0.000% | −0.345% | 0.250% | 2.69% | 3.35 | 73 / 3200 |
| RL seed 4 | 0.096% | 0.079% | −0.487% | 0.297% | 2.47% | 4.28 | 23 / 3200 |
| Fixed rule | **0.192%** | 0.128% | −0.681% | 0.513% | 3.04% | 3.81 | 291 / 3200 |
| Always hold | 0.006% | 0.000% | −0.879% | 0.658% | 4.53% | 0 | 0 |

RL mean return across seeds: 0.044% to 0.096%. RL fell back to the rule in 0 of
3,200 decisions per run.

**Reading:**
- **Negative result on return.** Every RL run earned less average return than
  the fixed rule.
- **Lower risk.** RL roughly halved the mean drawdown and proposed 3–14× fewer
  trades that the gate blocked.
- **Mostly in cash.** Its median return of 0% shows it often sells down to no
  shares and sits in cash. That is what a downside penalty on a noisy signal
  encourages. Lowering the penalty might trade risk back for return; this was
  not tried, to avoid tuning on these results.
- **Better than always-hold** on every metric except turnover.

## Behaviour on the canonical scenarios (`AGENTS_POLICY=rl`, via the API)

| Scenario | Fixed rule | RL policy |
|---|---|---|
| momentum_concentration | buy 5 → **blocked** (POSITION_LIMIT) | hold → allowed |
| quiet_market | hold | sell 5 → allowed |
| conflicting_signals | hold | sell 5 → allowed |

With RL enabled, the "strategy" choice no longer produces the blocked proposal
the demo script relies on. The learner's own "increase" choice still gets
blocked. Choose the mode deliberately before recording.

## Limitations

- The synthetic generator is mine: its drift, noise, and headline-matching
  probability set what can be learned.
- The state is coarse. The policy cannot see how close a buy would land to the
  20% cap, only the current weight bucket.
- There is one instrument per scenario, and the episodes are short.
- The learned values are not an explanation of why the policy acted.
