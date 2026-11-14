# 48-hour build plan

Updated team split: the user owns backend work using Codex for the API/simulator/risk gate and Claude for specialist agents and optional RL. A separate human teammate owns the frontend. TEAM_HANDOFF.md, CODEX_PLANNER.md, and CLAUDE_PLANNER.md contain the current ownership and override earlier assistant role assignments.

Goal: demonstrate how specialist analysis and an independent risk gate help a beginner understand a simulated investment decision.

Scope assumption: a solo builder or small team using a familiar web stack. Hours below are elapsed from project start. Include rest; move the rest block to suit your local start time.

**The finished demo**

One screen contains a fictional $10,000 portfolio, a clearly labeled simulated market event, three specialist cards, a proposed practice action, an independent risk decision, and a short explanation with one learning question.

The memorable interaction: optimistic news arrives, price swings increase, the strategy proposes increasing an already concentrated position, and the risk gate blocks the proposal. The learner sees why, compares alternatives, and explains the tradeoff.

Use a small synthetic dataset with fictional assets for the dependable core demo. Label it synthetic throughout. If permitted historical data is already available, it can support a separate replay, with sources and dates. Neither a synthetic scenario nor a small curated replay establishes real-market performance.

**Build responsibilities**

| Component | Input | Output | Implementation |
|---|---|---|---|
| Sentiment specialist | Provided headlines | Tone, cited headline IDs, conflicting evidence | Bounded model call or text classifier |
| Risk specialist | Prices and virtual holdings | Volatility, position concentration, illustrative loss amounts | Deterministic calculations |
| Strategy specialist | Specialist findings and portfolio | Hold or bounded allocation change, with rationale | Fixed policy first; replaceable with one RL policy |
| Independent risk gate | Proposed action and holdings | Allow/block plus exact rule reason | Deterministic code |
| Learning explanation | Recorded evidence, calculations, action, and gate result | Short explanation and a comprehension question | Template first; grounded model wording if time permits |

For demo purposes, set an illustrative maximum single-stock allocation of 20%, no borrowing or shorting, and a hold action. These are simulator design settings, not recommended personal investment limits. Reject an action that would exceed a limit; do not silently resize it. A risk gate limits permitted actions, not all possible losses.

Keep shared records simple: scenario ID, observation time, input evidence IDs, findings, proposed action, gate result, and version. Display missing inputs explicitly. Never ask a language model to calculate portfolio balances.

**Schedule**

| Elapsed hours | Work | Exit condition |
|---|---|---|
| 0–2 | Freeze the scope; choose familiar tools; sketch one screen; prepare three synthetic scenarios | One sentence defining success and a fixed demo script |
| 2–8 | Build the screen, virtual portfolio, scenario loading, and deterministic risk gate | A button produces a blocked or allowed action with correct arithmetic |
| 8–14 | Connect sentiment, risk, and strategy outputs; add explanations | One complete journey works from event to learning question |
| 14–18 | Implement all three scenarios; handle missing data and model failures | Positive/volatile, quiet/neutral, and conflicting-evidence scenarios all run |
| 18–24 | Rest and buffer | Working version saved before stopping |
| 24–30 | Optional RL experiment if the core works; otherwise finish core integration | A trained policy with a recorded comparison, or a clear decision to defer it |
| 30–36 | Observe two beginners; fix confusing language; test risky actions and arithmetic | Users can explain the risk gate's reason without coaching |
| 36–42 | Polish layout, prepare a local fallback, and rehearse the pitch | A reliable three-minute demo with no essential network dependency |
| 42–46 | Record a backup demo; package submission and limitations | Required submission materials ready |
| 46–48 | Final verification and submission buffer | Submit before the deadline; no new features |

**RL decision at hour 24**

If the core experience does not work, spend this block completing it. If RL is unfamiliar, budget the block for a research demonstration only; do not let it consume the final integration time.

For a genuine, bounded RL experiment, use one small policy in a synthetic replay environment. Observations can include current allocation, sentiment category, and volatility category. Actions can be hold, add a small permitted allocation, or reduce it. Rewards use subsequent simulated portfolio change after costs with a documented downside penalty. The independent gate still applies.

Train on multiple generated sequences and evaluate on different held-out seeds using identical rules for the RL policy and fixed-policy baseline. Record returns, maximum drawdown, turnover, and blocked proposals. Report the comparison honestly. Learning on synthetic sequences demonstrates the mechanism, not a market edge.

Hard cutoff: at hour 30, integrate a working policy or keep the fixed policy. Label the fixed-policy demo as rule-based; do not describe it as trained RL. Present the larger risk-aware RL swarm as the next research stage if it was not built.

**Verification checklist**

- [ ] The simulated status and synthetic data labels remain visible.
- [ ] Buying reduces cash and increases holdings by the expected amounts after costs.
- [ ] A blocked action leaves the portfolio unchanged.
- [ ] Exact-limit and over-limit allocations behave as intended.
- [ ] Borrowing and short positions are rejected.
- [ ] Zero or missing prices do not produce valid trades.
- [ ] Sentiment claims point to supplied headline evidence.
- [ ] The explanation matches the recorded gate decision and numbers.
- [ ] An unavailable model produces a clearly labeled fallback rather than an invented result.
- [ ] The app can run the core demo from local fixtures.
- [ ] The learner gets a question about risk or uncertainty, not a score based on profit.
- [ ] Any trained policy is distinguished from fixed rules and prerecorded output.

**Team split, if applicable**

- Interface/product: screen, learner flow, user testing, presentation.
- Backend/risk: portfolio arithmetic, independent gate, fixtures, verification.
- AI/research: sentiment extraction, strategy interface, optional RL experiment.

Agree on shared input/output fields during the first two hours and integrate by hour 8. A solo builder follows the same order and treats RL as optional unless the event requires it.

**Three-minute pitch**

0:00–0:25: Explain the beginner's problem: a headline does not explain portfolio consequences.

0:25–1:40: Run the scenario, show specialist disagreement, and demonstrate a blocked oversized action.

1:40–2:15: Compare a permitted alternative and show the learning question.

2:15–2:40: Explain which parts are deterministic, model-generated, and actually learned.

2:40–3:00: State what was tested, the limits of the data, and the next experiment.

Do not add brokerage connections, account login, live social feeds, a large stock universe, independently retraining agents, or automatic production updates during this build.

**First two hours checklist**

- [ ] Read the event rubric and submission requirements; identify whether trained RL is mandatory.
- [ ] Choose the one-screen demo and assign responsibilities.
- [ ] Define three fictional assets, virtual holdings, and three scenario fixtures.
- [ ] Fix the specialist output fields and action schema.
- [ ] Write the oversized-position example and its expected risk-gate result.
- [ ] Start building the portfolio and gate before integrating model calls.
