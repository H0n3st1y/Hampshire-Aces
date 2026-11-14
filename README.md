# Synthetic Investing Simulator

An educational, one-step investing simulator with specialist proposals and an independent deterministic risk gate. All three scenarios, assets, headlines, and USD balances are fictional. Every evaluation starts from the scenario's simulated $10,000 portfolio.

## Backend launch (Windows PowerShell)

Run from the project folder:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements.lock
backend/.venv/Scripts/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Python 3.12 on Windows is the verified environment; `requirements.lock` freezes that complete tested runtime and test environment. `requirements-dev.txt` is the direct dependency input when updating it. For runtime only, install `backend/requirements.txt`. No external services, accounts, API keys, research packages, trained artifacts, or paid models are required. Installing dependencies initially requires a package source; running the installed demo does not require internet access.

Open [interactive API docs](http://127.0.0.1:8000/docs) or [the scenario endpoint](http://127.0.0.1:8000/api/scenarios). Default operation attempts Claude's local modules with model calls disabled. Optional model settings belong to Claude's agents; see `backend/agents/README.md` when available. Do not enable model calls for the dependable offline demo.

For the backend's explicit emergency fallback mode, set this before launch:

```powershell
$env:AGENT_MODE = 'offline'
```

This bypasses specialist modules and visibly labels neutral sentiment, safety hold, and template lesson fallbacks in warnings. Explicit user increase/reduce actions still run through the real accounting and gate. Normal local-module mode is `AGENT_MODE=auto`; optional external model calls remain disabled unless separately enabled by Claude's configuration.

## Frontend teammate

Use `contracts/api-v1.md` and the complete JSON in `contracts/examples/`. The two endpoints are:

- `GET /api/scenarios`
- `POST /api/evaluate` with `{"schema_version":"1","scenario_id":"momentum_concentration","action":"increase"}`

Actions: `strategy`, `hold`, `increase`, `reduce`. Display mode labels and warnings accurately. An unavailable metric is null, not zero. Blocked actions are never executed or silently resized. Repeated requests restart from the initial portfolio; show only the response for the latest UI selection.

The default allowed browser origins are localhost/127.0.0.1 on ports 5173 and 3000. If the frontend is on another machine, agree on the backend computer's reachable IP and the frontend browser's exact origin, then launch with:

```powershell
$env:CORS_ORIGINS = 'http://FRONTEND_IP:5173'
backend/.venv/Scripts/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Use `http://BACKEND_IP:8000` in that frontend. Replace the placeholders; a teammate's localhost refers to their computer. A reachable address/firewall configuration has not yet been verified. No frontend implementation is included or modified here.

## Accounting and gate

Money uses integer USD cents and quantities use whole shares. Each allowed buy/sell pays one fixed $1.00 cost, with no slippage, taxes, dividends, or borrowing interest. Holds and rejected proposals pay zero. Total value reconciles exactly to cash plus quantity times decision price. Comparison outcomes mark both portfolios at the same hidden synthetic next-step price; those prices are excluded from sentiment/strategy observations.

The gate validates proposal shape, permitted symbol, positive price data, sufficient cash including costs, sufficient holdings, and a 20% single-stock cap on the post-fee portfolio. The cap comparison uses integer arithmetic. A proposal that buys up to 20% before costs may exceed the limit after the $1 fee. Holds remain valid without increasing exposure, even if a preexisting holding is above the cap. Missing required history makes the gate unavailable, including for hold.

Daily volatility is the sample standard deviation of the supplied consecutive daily simple returns, unannualized, requiring at least three prices. Six observations give five return intervals. Missing or invalid history produces null volatility and a limitation; nothing is zero-filled. Invalid starting balances or missing private outcomes are corrupt fixtures and fail validation rather than fabricate portfolio values.

The limit is an illustrative rule and cannot prevent all future losses. These synthetic outcomes are demonstrations, not evidence of strategy performance or personalized investment advice. No RL model is trained by this backend; `policy_mode=rl` is reserved for an actual artifact delivered through Claude's interface.

## Claude integration and research

Exact schemas: `backend/contracts.py`; interface guide: `contracts/agents-v1.md`. Claude owns `backend/agents/` and optional `research/`. Local agent calls run in disposable processes, default 3 seconds each including import, maximum output 64 KiB. `AGENT_TIMEOUT_SECONDS` can be configured between 0.1 and 10 seconds. Schema, role, evidence, timeout, import, or execution failures produce explicit backend fallbacks. This isolates failures and copied inputs; it is a cooperative local-code boundary, not a security boundary against malicious modules reading workspace files.

`backend.service.build_observation(fixture)` creates the decision-time agent observation. `backend.simulation.simulate(fixture, proposal)` (also `research_step`) is the production research adapter returning gate, immediate portfolio, comparison, and proposed weight. Research must keep the fixture's private future price in its environment and supply only the observation to policies. This is a stateless one-step adapter, not a multi-step Gym environment. Reuse it for exact production costs and risk decisions; optional training packages must stay outside startup imports.

## Checks and examples

```powershell
backend/.venv/Scripts/python -m pytest backend/tests -q
backend/.venv/Scripts/python -m pytest backend/agents/tests -q
backend/.venv/Scripts/python -m backend.scripts.export_examples
backend/.venv/Scripts/python -m backend.scripts.smoke
```

Run the HTTP smoke command while the server is running. The example exporter is deterministic and forces labeled backend fallbacks without editing process-wide settings. It also exports machine-readable JSON Schemas under `contracts/schemas/`. `unavailable.json` uses a controlled missing-history variant of quiet_market; it is not a fourth selectable scenario. Samples have stable example evaluation IDs; real requests receive unique IDs. `contracts/scenarios.json` contains private future outcomes and is not a frontend mock or agent input.

Actual checks, launch verification, delivered files, limitations, and teammate requests are recorded in `docs/CODEX_STATUS.md`. Frontend integration, beginner walkthroughs, optional model calls, and any trained RL artifact must be verified separately before claiming them as complete.
