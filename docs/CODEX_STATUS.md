# Codex backend status

Updated November 14, 2026, America/New_York. Backend contract and core are delivered. The original 48-hour clock has not restarted. The workspace does not record an authoritative event start time, so this report maps actual deliveries to the existing checkpoints without inventing elapsed hours.

## Delivered files

| Files | Delivered behavior |
|---|---|
| `contracts/api-v1.md` | Frozen frontend API, units, nullability, modes, stateless requests, errors, arithmetic examples, CORS |
| `contracts/agents-v1.md`, `backend/contracts.py` | Exact strict public/internal schemas and Claude callable boundary |
| `contracts/scenarios.json` | Three clearly synthetic canonical fixtures; private future outcome separated from observations |
| `contracts/examples/` | Complete catalog, allowed, blocked, unavailable, hold, offline strategy, and 400-error JSON |
| `contracts/schemas/` | Machine-readable JSON Schemas for public request/responses and internal agent records |
| `backend/main.py`, `backend/fixtures.py` | FastAPI endpoints, validated fixtures, allowlisted public catalog, 400/500 handling, local CORS |
| `backend/metrics.py`, `backend/simulation.py` | Sample daily volatility, exact cent accounting, fixed costs, independent gate, shared research adapter |
| `backend/integration.py`, `backend/service.py` | Copied observations, bounded agent processes, validated outputs/evidence, coach facts, explicit fallbacks |
| `backend/tests/test_simulation.py`, `test_api.py`, `test_integration.py` | Calculations, rejection rules, missing data, stateless repeats/concurrency, Claude integration, failures and isolation |
| `backend/requirements.txt`, `requirements-dev.txt`, `requirements.lock`, `.gitignore` | Runtime/dev inputs and complete tested Windows/Python 3.12 environment lock |
| `backend/scripts/export_examples.py`, `smoke.py`, `snapshot.py` | Reproducible samples/schemas, live HTTP check, source-only backup |
| `README.md` | Setup, local/LAN connection instructions, assumptions, modes, research integration, limitations |

Codex has not edited `backend/agents/`, `research/`, `frontend/`, or `docs/CLAUDE_STATUS.md`. Claude's delivered agents and tests were read and exercised. No frontend implementation was present or created. No RL model was trained or claimed.

## Actual checks

Run from the project root:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests backend/agents/tests -q
backend/.venv/Scripts/python -m pip check
backend/.venv/Scripts/python -m backend.scripts.export_examples
backend/.venv/Scripts/python -m backend.scripts.smoke
```

- Fresh isolated environment created and installed successfully. Python 3.12.10, Windows. Full dependency versions frozen in `backend/requirements.lock`.
- Combined suite: **153 passed** (106 backend checks plus 47 existing Claude checks). One deprecation warning comes from the installed Starlette/AnyIO test adapter; no failing checks.
- `pip check`: no broken requirements.
- Example exporter completed. All eight exported schemas exactly match current models. Catalog and five evaluation samples exactly match production offline responses after substituting example IDs.
- Running HTTP server checked through actual network requests: catalog, all three scenarios × four actions, repeated evaluations with unique IDs and identical accounting, malformed action HTTP400, and local browser CORS all passed.
- Actual Claude modules run through disposable processes for all three strategy choices: ALFA proposes buy5 and is blocked; BETA holds; GAMMA's conflicting headlines produce hold and its conflict lesson. Modes are `fixture` / `rule_based` / `template`.
- Gate tests cover $1 fees, valid buys/sells/hold, insufficient cash, overselling, invalid prices, exact 20% boundaries, fee-denominator violations, unknown symbols, malformed/bool/fractional quantities, missing/stale/null history, and unchanged blocked portfolios.
- Failure tests cover unavailable modules, malformed output, invented evidence, wrong roles/modes, oversized output, timeouts with worker cleanup, generic server errors without secrets, and input mutation isolation.
- Outcome-leakage check: changing the private next price does not change either agent observation. Future keys are excluded recursively; sentiment/strategy receive copies and coach receives facts only after gating/calculation.

Hand checks: momentum increase leaves cash820000/shares18, executed outcome null, hold973000; momentum reduce leaves cash869900/shares13, immediate999900, outcome980400. Quiet increase leaves cash849900/shares15, immediate999900, outcome1001400 versus hold1001000. GAMMA increase to20 shares is blocked: 200000 / 999900 exceeds20% after the fee.

## Launch and running instance

The backend is currently running at **http://127.0.0.1:8000**, bound locally, server process **24716** (Windows environment launcher22464). Documentation: http://127.0.0.1:8000/docs. It uses the isolated environment, `AGENT_MODE=auto`, `AGENTS_MODEL_ENABLED=0`, `AGENTS_POLICY=rule_based`; no external provider calls are enabled. Process IDs and logs are under `backend/.logs/`.

To launch a new instance after stopping the current one:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements.lock
$env:AGENT_MODE = 'auto'
$env:AGENTS_MODEL_ENABLED = '0'
$env:AGENTS_POLICY = 'rule_based'
backend/.venv/Scripts/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

To force emergency fallbacks, use `AGENT_MODE=offline`. Explicit hold/increase/reduce still exercise the real gate and simulator. Local modules require no network. Each agent call has a default3-second process deadline, including imports; output limit64KiB; maximum4 active workers. Configurable `AGENT_TIMEOUT_SECONDS` range0.1–10 seconds. Warnings disclose all fallbacks.

No git repository existed; no branch was switched or reset. `backend/scripts/snapshot.py` saved and verified `backend/releases/known-working-backend-v1.zip` (54 source/contract/document files) plus its SHA256, excluding environment, caches, logs, and research. ZIP integrity and every source hash were checked. It includes observed Claude sources as a read-only backup, not a competing implementation. Restore into a separate folder and follow README launch steps.

## Frontend teammate coordination

- Use `contracts/api-v1.md`, `contracts/examples/`, and optionally `contracts/schemas/`. Do not bundle private `contracts/scenarios.json` into the frontend.
- Base URL on this computer is `http://127.0.0.1:8000`. Default CORS permits localhost and127.0.0.1 ports5173 and3000. Other origins must be configured via comma-separated `CORS_ORIGINS` before launch.
- If the teammate uses another computer, agree the backend's reachable LAN IP and exact frontend origin, bind `--host 0.0.0.0`, and configure CORS per README. No LAN address or firewall path has been verified; their localhost cannot reach this backend.
- Display synthetic/simulated labels, actual mode fields, warnings, null unavailable metrics, unchanged rejected portfolios, and the same-starting-portfolio comparison behavior. Ignore older responses when selections change.
- No actual browser frontend → backend journey or beginner walkthrough has been observed; those hour14/hour36 checkpoints require the human teammate/user. Backend live HTTP compatibility is verified.

## Claude coordination and remaining corrections

The prior `docs/CLAUDE_STATUS.md` described provisional inputs before the backend existed. Frozen interfaces now exist. No edit to Claude's status was made.

- Import paths are `backend.agents.sentiment.analyze`, `backend.agents.strategy.propose`, `backend.agents.coach.explain`.
- Existing `sentiment_label` / `headline_assessments` were adopted internally before initial freeze. They are validated and withheld from the public response. Headlines are keyword-analyzed by your current offline module, accurately labeled fixture.
- Observation supplies `historical_prices_cents`, `permitted.symbols`, `permitted.actions`, and **`permitted.action_quantity`**. Please consume that exact quantity. Current strategy falls back to5% sizing, which coincides at5 shares in all canonical fixtures; this remains a general interface correction for Claude. Also normalize the exact history field.
- Coach receives **`CoachFacts`**: verified public facts before lesson plus internal-only `action` and validated `sentiment_label`. This additive clarification is documented in agents-v1; public v1 stays unchanged. The conflicting-headline lesson works.
- **Observed coach defect:** `_holding_lesson` passes literal `'blocked'` into `_outcome_sentence`, so an allowed hold says there is no executed outcome. Please pass the recorded gate status. Backend rejects that contradictory phrase when an executed outcome exists and supplies a truthful labeled template fallback. Tests cover corrected public behavior; the Claude source correction remains pending.
- **Coach clarity request:** concentration percentages formatted to one decimal can read20.0% above20.0% for GAMMA's fee boundary. Please show enough precision or explain that fees push it just above the limit. Root gate/metrics retain full precision.
- Evidence IDs are headline IDs plus `prices:SYMBOL` and `portfolio:initial`; all references must resolve. Rule IDs and exact schemas are in agents-v1.
- `backend.simulation.simulate(fixture, proposal)` / `research_step` is ready and uses production fee, gate, and accounting. `backend.service.build_observation(fixture)` supplies policy input. Research owns its reward path and must not pass future outcomes to the policy. Startup imports no research packages.
- Reviewed `research/README.md` requests for reset/step, seeded sequence generation, and episodes. The delivered adapter is deliberately stateless and one-step, matching the core demo; reset, seeded generators, and multi-step episode wrappers are not implemented. Claude can wrap the shared adapter in `research/` without duplicating its arithmetic or gate. This does not block the three-scenario core.
- Optional `anthropic` dependency reviewed: **not required or installed for the core demo**. External model use is unverified; provider8-second timeout exceeds backend default3-second bound. Any later model configuration must coordinate deadlines and retain fallbacks.

## Remaining milestone work outside the completed backend core

Frontend connection and latest-selection handling; agreed LAN address if needed; actual beginner walkthroughs; rehearsal/backup recording; optional RL only if Claude delivers a verified artifact within the original hour30 cutoff. No external submission performed. Keep public API and feature scope frozen while resolving observed integration defects.
