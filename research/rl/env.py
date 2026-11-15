"""Multi-step synthetic environment wrapping Codex's production simulation adapter.

Each step builds a ScenarioFixture, gives the policy ONLY the decision-time
Observation (backend.service.build_observation) plus Claude's sentiment result,
then calls backend.simulation.simulate(fixture, proposal), which applies the
production fee, gate, and accounting. The next step starts from the adapter's
post-action portfolio marked at the revealed next price; the rebuilt total is
checked against the adapter's own end value so no arithmetic can drift.

Synthetic generator (documented assumptions, not market data):
- volatility regime per episode: daily sigma in {0.008, 0.02, 0.04}
- latent signal per step s in {+1, 0, -1}; next return = 0.012*s + sigma*N(0,1)
- each of 2 headlines matches s with prob 0.7, else a random tone
So sentiment is informative but noisy, and high volatility can swamp it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from backend.agents import sentiment
from backend.contracts import Portfolio, Position, ScenarioFixture
from backend.service import build_observation
from backend.simulation import simulate

SYMBOL, NAME = "SIMX", "Synthetic Instrument X (fictional)"
SIGMAS = (0.008, 0.02, 0.04)
DRIFT = 0.012
HEADLINE_MATCH_PROB = 0.7
HISTORY_LEN = 6
START_VALUE_CENTS = 1_000_000

_TEMPLATES = {
    "positive": [
        "SYNTHETIC: SIMX reports strong fictional demand and record orders.",
        "SYNTHETIC: Analysts upgrade SIMX after a fictional product win.",
        "SYNTHETIC: SIMX raises its fictional outlook on growth.",
    ],
    "negative": [
        "SYNTHETIC: SIMX warns of a fictional supply shortage and delays.",
        "SYNTHETIC: Regulators open a fictional probe into SIMX.",
        "SYNTHETIC: SIMX cuts its fictional outlook as orders decline.",
    ],
    "neutral": [
        "SYNTHETIC: SIMX confirms its fictional reporting schedule.",
        "SYNTHETIC: SIMX publishes a routine fictional operational update.",
        "SYNTHETIC: SIMX names a new fictional board secretary.",
    ],
}
_TONE_OF = {1: "positive", 0: "neutral", -1: "negative"}


@dataclass
class StepResult:
    proposal: dict
    gate_status: str
    executed_trade: bool
    shares_traded: int
    value_before: int
    value_after: int


class Episode:
    def __init__(self, seed: int, length: int = 8):
        self.rng = random.Random(seed)
        self.length = length
        self.t = 0
        self.sigma = self.rng.choice(SIGMAS)
        self.action_quantity = self.rng.randint(3, 7)
        price = self.rng.randint(5_000, 20_000)
        prices = [price]
        for _ in range(HISTORY_LEN - 1):
            prices.append(self._next_price(prices[-1], self.rng.choice((1, 0, -1))))
        self.history = prices
        weight = self.rng.choice((0.0, 0.05, 0.10, 0.15, 0.18, 0.19))
        qty = int(weight * START_VALUE_CENTS) // prices[-1]
        self.portfolio = Portfolio(
            cash_cents=START_VALUE_CENTS - qty * prices[-1],
            positions=[Position(symbol=SYMBOL, name=NAME, quantity=qty, price_cents=prices[-1], value_cents=qty * prices[-1])],
            total_value_cents=START_VALUE_CENTS - qty * prices[-1] + qty * prices[-1],
        )
        self._draw_step()

    def _next_price(self, price: int, signal: int) -> int:
        ret = DRIFT * signal + self.sigma * self.rng.gauss(0, 1)
        return max(100, round(price * (1 + ret)))

    def _draw_step(self) -> None:
        self.signal = self.rng.choice((1, 0, -1))
        self.headlines = []
        for i in range(2):
            tone = _TONE_OF[self.signal] if self.rng.random() < HEADLINE_MATCH_PROB else self.rng.choice(list(_TEMPLATES))
            self.headlines.append({
                "id": f"sim:{self.t}:{i}",
                "text": self.rng.choice(_TEMPLATES[tone]),
                "published_at": f"2026-01-{self.t + 1:02d}T10:00:00Z",
            })
        self.next_price = self._next_price(self.history[-1], self.signal)

    def _fixture(self) -> ScenarioFixture:
        return ScenarioFixture(
            id=f"sim-step-{self.t}", title="Synthetic RL training step", as_of=f"2026-01-{self.t + 1:02d}T21:00:00Z",
            synthetic=True, summary="Generated synthetic step for offline RL research.",
            headlines=self.headlines, initial_portfolio=self.portfolio,
            instrument={"symbol": SYMBOL, "name": NAME},
            historical_prices_cents=list(self.history[-HISTORY_LEN:]),
            next_price_cents=self.next_price, action_quantity=self.action_quantity,
        )

    def observe(self) -> tuple[dict, dict]:
        """Decision-time observation and sentiment. Contains no next price or signal."""
        obs = build_observation(self._fixture()).model_dump()
        return obs, sentiment.analyze(obs)

    def step(self, proposal: dict) -> StepResult:
        result = simulate(self._fixture(), proposal)
        before = self.portfolio.total_value_cents
        executed = result.comparison.end_value_if_executed_cents
        after_value = executed if executed is not None else result.comparison.end_value_if_hold_cents
        traded = result.gate.status == "allowed" and proposal["type"] != "hold"

        # Carry the adapter's post-action holdings forward at the revealed price.
        held = result.portfolio_after_action
        pos = held.positions[0]
        new_pos = Position(symbol=SYMBOL, name=NAME, quantity=pos.quantity, price_cents=self.next_price,
                           value_cents=pos.quantity * self.next_price)
        new_total = held.cash_cents + new_pos.value_cents
        if new_total != after_value:
            raise AssertionError("Rebuilt portfolio does not match the adapter's end value.")
        self.portfolio = Portfolio(cash_cents=held.cash_cents, positions=[new_pos], total_value_cents=new_total)
        self.history.append(self.next_price)
        self.t += 1
        if self.t < self.length:
            self._draw_step()
        return StepResult(proposal, result.gate.status, traded,
                          proposal["quantity"] if traded else 0, before, after_value)

    @property
    def done(self) -> bool:
        return self.t >= self.length
