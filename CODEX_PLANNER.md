# Codex assignment: backend core, risk, simulation, API integration

Read the revised TEAM_HANDOFF.md first. The user owns backend work using Codex and Claude. A separate human teammate owns frontend/. Claude owns backend/agents/ and research/. You own the rest of backend/, contracts/, root README, and docs/CODEX_STATUS.md. This assignment replaces the earlier split; elapsed deadlines do not restart.

Do not edit Claude's directories or the frontend. Preserve existing work. Codex alone manages shared backend dependency manifests and lockfiles; review Claude's dependency requests from their status file.

**Deliverables**

- Public /api/scenarios and /api/evaluate endpoints with stable example responses.
- Canonical synthetic fixtures, portfolio arithmetic, costs, comparison outcomes, and independent risk controls.
- Decision-time observation construction, internal module schemas, validation, and agent orchestration.
- Integration of Claude's sentiment, strategy, and coach modules with labeled emergency fallbacks.
- A reusable simulation adapter for Claude's optional RL research.
- Meaningful tests, frontend connection support, launch instructions, and limitations.

**Hours 0-2: unblock both contributors**

- [ ] Inspect the workspace and existing instructions.
- [ ] Create contracts/api-v1.md, scenarios.json, and complete allowed/blocked/unavailable examples.
- [ ] Create backend/contracts.py and contracts/agents-v1.md for Claude's functions, following TEAM_HANDOFF.md.
- [ ] Separate future outcomes from policy-visible observations.
- [ ] Give the frontend teammate the API examples and Claude the internal schema locations.
- [ ] Record run/setup details in docs/CODEX_STATUS.md.

Acceptance: the teammate can build the UI from sample responses while Claude independently builds callable modules.

**Hours 2-8: core simulator and first integration**

- [ ] Scaffold the backend without creating files inside Claude's owned directories.
- [ ] Implement integer-cent/whole-share portfolio accounting and documented transaction costs.
- [ ] Implement explicit hold/increase/reduce user actions and call Claude's policy for the strategy choice.
- [ ] Enforce positive prices, cash/holding availability, no borrowing or shorting, and the illustrative 20% position cap after costs.
- [ ] Reject blocked proposals without hidden resizing; leave holdings and cash unchanged.
- [ ] Wire Claude's initial modules. Until ready, use a minimal labeled hold/template fallback in your own code, not a competing strategy implementation.
- [ ] Serve the scenario endpoint and first evaluation; validate the frontend connection by hour 8.
- [ ] Supply the correct API address and browser-access configuration. If the teammate uses another machine, document an agreed reachable address; localhost on their device is not your backend.

Acceptance: arithmetic reconciles, blocked actions cannot execute, Claude's modules are callable, and the frontend can retrieve a scenario.

**Hours 8-14: complete orchestration**

- [ ] Calculate volatility and concentration using documented methods.
- [ ] Assemble copied or immutable observations excluding future prices.
- [ ] Invoke Claude's sentiment/strategy modules with bounded calls and validate output schemas, symbols, quantities, and evidence references.
- [ ] Apply the gate to every proposal, regardless of its originating model.
- [ ] Compute portfolio and comparison results before sending verified facts to Claude's coach.
- [ ] Implement labeled emergency neutral/hold/template fallback on module failure, or unavailable on insufficient required data.
- [ ] Return truthful model-mode fields and resolve evidence IDs.
- [ ] Keep evaluations stateless and independent of repeated requests.
- [ ] Coordinate with Claude on module defects and the teammate on the first complete UI journey.

Acceptance: the full experience uses actual backend calculations and explains the gate's recorded decision.

**Hours 14-18: verification and research adapter**

- [ ] Complete all three scenarios and action choices.
- [ ] Test correct buys/sells, hold, insufficient cash, overselling, invalid prices, cap boundaries, over-limit proposals, malformed requests, and repeated evaluations.
- [ ] Verify future observations cannot enter the policy and blocked actions leave the portfolio unchanged.
- [ ] Test schema failures, timeouts, and offline operation.
- [ ] Expose a documented callable simulation adapter reusing the exact production gate, costs, and balance functions for Claude's research.
- [ ] Save a known working version before rest/buffer.

**Hours 24-30: harden while Claude handles optional RL**

- [ ] Resolve backend/frontend integration problems and strengthen error handling.
- [ ] Support Claude's use of the simulation adapter without duplicating training work.
- [ ] Review runtime dependency requests, model loading, and the actual evaluation report.
- [ ] Integrate a reliable trained artifact through the existing policy interface only if ready by hour 30; otherwise retain Claude's fixed policy.
- [ ] Verify ordinary startup works without optional training packages or artifacts.

Claude owns the experiment. Keep the public contract stable and mode labels accurate. Do not describe a heuristic as trained RL.

**Hours 30-42: full-system checks and documentation**

- [ ] Resolve issues observed during actual beginner walkthroughs.
- [ ] Verify the running integrated app, not just isolated endpoints.
- [ ] Check documented launch steps and default operation without paid services.
- [ ] Document synthetic data, costs, rules versus trained behavior, and known limitations in README.md.
- [ ] Give the user and frontend teammate accurate backend notes for their demo script.
- [ ] Confirm a known working version is ready for recording.

**Hours 42-48: submission support**

Fix critical defects only and verify affected behavior. Provide source, launch instructions, checks performed, final policy mode, and limitations. Do not submit externally unless authorized.

Done means the teammate's frontend can complete all scenarios, arithmetic and gate tests pass, Claude's modules are integrated, offline fallback is explicit, and the demo is reproducible. Neither frontend implementation nor RL training is your assignment.
