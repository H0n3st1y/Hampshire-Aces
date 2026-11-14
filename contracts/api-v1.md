# Public API contract v1

This is an educational simulator using explicitly synthetic headlines, fictional assets, and simulated USD. Every scenario starts with $10,000. No accounts, brokerage execution, or live market services are involved.

The API is stateless. Each evaluation restarts at the selected scenario's initial portfolio. A second request never applies a second trade. Show this behavior in the UI, and display only the response for the user's latest selection when requests finish out of order.

## Connection

Default base URL: `http://127.0.0.1:8000`. JSON request and response bodies use UTF-8. The public endpoints require no API key. Interactive API documentation is at `/docs`; the machine-readable schema is at `/openapi.json`.

Local browser origins allowed by default: `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`, and `http://127.0.0.1:3000`. A teammate on a different computer needs a reachable host address and an explicitly configured browser origin; their localhost points to their own computer. See the root README for launch and LAN settings.

## Units and nulls

- Money is integer USD cents. `10000` means $100.00.
- Quantities are whole integer shares. No borrowing, short sales, or fractional shares.
- Ratios are fractions: `0.20` means 20%.
- Times are ISO-8601 UTC strings.
- Nullable fields are `metrics.daily_volatility`, `metrics.position_weight_proposed`, `comparison.end_value_if_executed_cents`, and `proposal.symbol` (null for hold). No other response fields are nullable.
- Unavailable statistics have a corresponding limitation or warning. They must never be rendered as zero.

## GET /api/scenarios

Returns HTTP 200:

```json
{"schema_version":"1","scenarios":["Scenario objects described below"]}
```

Each scenario has these fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable ID accepted by `/api/evaluate` |
| `title` | string | Explicitly synthetic display title |
| `as_of` | UTC timestamp | Decision time |
| `synthetic` | literal `true` | Must be displayed accurately |
| `summary` | string | Decision-time scenario description |
| `headlines` | array | Objects with `id`, `text`, `published_at`; published at or before `as_of` |
| `initial_portfolio` | Portfolio | The same starting portfolio used for every comparison |

The three IDs are `momentum_concentration`, `quiet_market`, and `conflicting_signals`. The complete response is in `contracts/examples/scenarios.json`. `contracts/scenarios.json` is the canonical simulator fixture, which additionally contains private next-step prices; it is not the response body and must not be bundled into an agent prompt or frontend mock.

## POST /api/evaluate

Request:

```json
{"schema_version":"1","scenario_id":"momentum_concentration","action":"increase"}
```

All three fields are required; unknown fields and values are rejected. `action` must be one of:

| Action | Proposal source |
|---|---|
| `strategy` | Claude's strategy module, or a clearly labeled emergency hold if unavailable |
| `hold` | Backend constructs a zero-quantity hold |
| `increase` | Backend proposes buying exactly five shares of the scenario instrument |
| `reduce` | Backend proposes selling exactly five shares of the scenario instrument |

Actions are never secretly resized to fit a limit. The independent backend gate validates every proposal, including a strategy proposal. A favorable headline or model output cannot approve a trade.

HTTP 200 response fields:

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | literal `"1"` | Contract version |
| `scenario_id` | string | Selected scenario |
| `evaluation_id` | string | Unique request result ID; not a persistent account ID |
| `synthetic` | literal `true` | All money/data are simulated |
| `as_of` | UTC timestamp | Decision time |
| `analysis_mode` | `"model"` or `"fixture"` | Actual sentiment source; emergency neutral uses fixture |
| `policy_mode` | `"rule_based"` or `"rl"` | Actual proposal source; explicit user actions and emergency hold use rule_based |
| `explanation_mode` | `"template"` or `"model"` | Actual lesson source |
| `specialists` | array of Specialist | Sentiment, risk, and strategy records |
| `evidence` | array of Evidence | Evidence IDs referenced by specialist records |
| `metrics` | Metrics | Backend-calculated values |
| `proposal` | Proposal | Exact proposed action before gate |
| `gate` | Gate | Independent deterministic decision |
| `portfolio_before` | Portfolio | Starting balances |
| `portfolio_after_action` | Portfolio | Immediate balances at the decision price; unchanged if blocked/unavailable |
| `comparison` | Comparison | One-step hypothetical price outcomes |
| `lesson` | Lesson | Explanation and learning question grounded in recorded results |
| `warnings` | string array | Fallbacks, missing data, and limitations to display |

### Nested objects

`Portfolio`:

```text
cash_cents: integer >= 0
positions: [{symbol: string, name: string, quantity: integer >= 0,
             price_cents: integer > 0, value_cents: integer >= 0}]
total_value_cents: integer > 0
```

Every position value equals quantity times price. Total value equals cash plus position values. At execution, a permitted buy or sell costs exactly 100 cents ($1) once; hold, blocked, and unavailable proposals cost zero. There is no slippage, borrowing interest, dividend, or tax model.

`Specialist`: `{role: "sentiment" | "risk" | "strategy", summary: string, evidence_ids: string[], limitations: string[]}`. Evidence references must resolve to the response's evidence array. They are identifiers, not URLs.

`Evidence`: `{id: string, kind: "headline" | "price_series" | "portfolio", label: string, description: string}`. Headline IDs come from the scenario. Backend price evidence uses `prices:ALFA`, `prices:BETA`, or `prices:GAMMA`; starting portfolio evidence uses `portfolio:initial`.

`Metrics`:

```text
daily_volatility: number | null
position_weight_before: number
position_weight_proposed: number | null
lookback_days: integer >= 0
```

Volatility is the sample standard deviation (`n-1` denominator) of daily simple returns `p[i] / p[i-1] - 1`, unannualized. At least three positive daily prices (two returns) are required. `lookback_days` is the number of daily return intervals, normally five for the six-price fixtures. Weights use the scenario instrument's value divided by portfolio total; proposed weight includes the trading fee even if the gate blocks the proposal. An uncomputable proposed weight is null.

`Proposal`: `{type: "hold" | "buy" | "sell", symbol: string | null, quantity: integer, reason: string}`. Hold uses symbol null and quantity 0; buys/sells use the permitted instrument and a positive whole-share quantity.

`Gate`: `{status: "allowed" | "blocked" | "unavailable", rule_ids: string[], explanation: string, max_position_weight: 0.20}`. Required data must be valid and sufficient. Missing decision history produces unavailable, including for hold. The core fixtures always contain valid starting marks and a valid private next-step price. The gate checks positive prices, the allowed instrument, sufficient cash including fees, sufficient holdings, and a maximum 20% single-stock weight after costs. These illustrative limits constrain actions and cannot prevent future losses.

`Comparison`:

```text
end_value_if_executed_cents: integer | null
end_value_if_hold_cents: integer
execution_cost_cents: integer >= 0
explanation: string
```

Only allowed proposals have an executed outcome; allowed hold has the same outcome as holding. Blocked/unavailable proposals have null executed outcome and zero cost, even if their hypothetical future price would have been favorable. The hold outcome still marks the starting holdings at the synthetic next-step price, so it can differ from the starting $10,000. Future outcomes are introduced after the proposal and gate, never into sentiment/strategy observations.

`Lesson`: `{concept: string, explanation: string, question: string, choices: [{id: string, text: string}], correct_choice_id: string, feedback: string}`. The correct ID must name one of the unique choice IDs. The coach explains verified results and cannot change balances or gate status.

## Error responses

Unknown scenario, unknown action, unknown version, missing fields, extra fields, invalid JSON, or otherwise malformed input return HTTP 400:

```json
{"error":{"code":"INVALID_REQUEST","message":"Invalid request."}}
```

The `message` may provide a safe explanation; clients must branch on HTTP status and `error.code`, not exact wording. Unexpected failures return HTTP 500 with a generic error and no internal details:

```json
{"error":{"code":"INTERNAL_ERROR","message":"An unexpected server error occurred."}}
```

Missing sufficient history in a known scenario is a valid HTTP 200 evaluation with `gate.status: "unavailable"`, unchanged balances, null executed outcome, and an explicit limitation. It is not a fabricated zero-volatility evaluation.

## Hand-checked arithmetic

All starting portfolios total 1,000,000 cents; the decision price is 10,000 cents and action size is five shares.

| Scenario/action | Gate | Immediate cash | Immediate shares/value | Immediate total | Executed next-step total | Hold next-step total |
|---|---|---:|---|---:|---:|---:|
| momentum/increase | blocked | 820000 | 18 / 180000 | 1000000 | null | 973000 |
| momentum/reduce | allowed | 869900 | 13 / 130000 | 999900 | 980400 | 973000 |
| quiet/increase | allowed | 849900 | 15 / 150000 | 999900 | 1001400 | 1001000 |
| quiet/reduce | allowed | 949900 | 5 / 50000 | 999900 | 1000400 | 1001000 |
| conflicting/increase | blocked | 850000 | 15 / 150000 | 1000000 | null | 992500 |
| conflicting/reduce | allowed | 899900 | 10 / 100000 | 999900 | 994900 | 992500 |

For momentum/increase, proposed concentration is `230000 / 999900`, above 20%. For conflicting/increase it is `200000 / 999900`, also above 20% because the fee reduces the denominator. All allowed holds preserve the starting balances and cost zero.

## Integration bundle

The frontend teammate needs this contract and `contracts/examples/` response JSON files, not the private canonical fixture. Claude needs `contracts/agents-v1.md` and `backend/contracts.py`. No names or units should change without a documented migration coordinated with consumers. The examples include allowed, blocked, and unavailable results; unavailable is a controlled missing-history test variant, not a fourth selectable scenario.
