"""Local, clearly synthetic test observations owned by Claude.

These are NOT the canonical fixtures (Codex owns contracts/scenarios.json).
They mirror the three scenario types in TEAM_HANDOFF.md so the agent modules
can be built and tested before the contracts freeze. Metrics below are
hand-entered stand-ins for Codex-calculated values; agents never compute them.
"""

import copy


def _portfolio(cash, symbol, name, qty, price):
    value = qty * price
    return {
        "cash_cents": cash,
        "positions": [{"symbol": symbol, "name": name, "quantity": qty, "price_cents": price, "value_cents": value}],
        "total_value_cents": cash + value,
    }


POSITIVE_CONCENTRATED = {
    "scenario_id": "local-positive-concentration",
    "as_of": "2026-03-02T21:00:00Z",
    "focus_symbol": "NOVA",
    "headlines": [
        {"id": "h1", "text": "Novalight Robotics beats quarterly estimates as orders surge", "published_at": "2026-03-02T13:00:00Z"},
        {"id": "h2", "text": "Analysts upgrade Novalight after record delivery numbers", "published_at": "2026-03-02T15:30:00Z"},
    ],
    "price_history": {"NOVA": [{"date": f"2026-02-{d:02d}", "price_cents": p} for d, p in zip(range(16, 28), [10400, 10850, 10300, 11200, 10900, 11650, 11100, 12050, 11700, 12400, 11900, 12500])]},
    "portfolio": _portfolio(812500, "NOVA", "Novalight Robotics (fictional)", 15, 12500),
    "metrics": {"daily_volatility": 0.041, "position_weight_before": 0.1875, "lookback_days": 11},
    "permitted": {"symbols": ["NOVA"], "actions": ["hold", "buy", "sell"]},
    "action_settings": {"step_value_cents": 50000},
    "evidence": [
        {"id": "px-NOVA", "kind": "price_series", "label": "NOVA daily prices", "description": "12 daily closes"},
        {"id": "pf-before", "kind": "portfolio", "label": "Starting portfolio", "description": "Fictional $10,000"},
    ],
}

QUIET_NEUTRAL = {
    "scenario_id": "local-quiet-neutral",
    "as_of": "2026-05-11T21:00:00Z",
    "focus_symbol": "CALM",
    "headlines": [
        {"id": "q1", "text": "Calmwater Utilities schedules annual shareholder meeting", "published_at": "2026-05-11T12:00:00Z"},
        {"id": "q2", "text": "Calmwater Utilities names new board secretary", "published_at": "2026-05-11T14:00:00Z"},
    ],
    "portfolio": _portfolio(900000, "CALM", "Calmwater Utilities (fictional)", 20, 5000),
    "metrics": {"daily_volatility": 0.006, "position_weight_before": 0.10, "lookback_days": 11},
    "permitted": {"symbols": ["CALM"], "actions": ["hold", "buy", "sell"]},
    "action_settings": {"step_value_cents": 50000},
    "evidence": [{"id": "px-CALM", "kind": "price_series", "label": "CALM daily prices", "description": "12 daily closes"}],
}

CONFLICTING = {
    "scenario_id": "local-conflicting",
    "as_of": "2026-07-20T21:00:00Z",
    "focus_symbol": "VOLT",
    "headlines": [
        {"id": "c1", "text": "Voltaic Grid wins large municipal battery contract", "published_at": "2026-07-20T13:00:00Z"},
        {"id": "c2", "text": "Regulators open probe into Voltaic Grid safety recall", "published_at": "2026-07-20T16:00:00Z"},
    ],
    "portfolio": _portfolio(850000, "VOLT", "Voltaic Grid (fictional)", 10, 15000),
    "metrics": {"daily_volatility": 0.022, "position_weight_before": 0.15, "lookback_days": 11},
    "permitted": {"symbols": ["VOLT"], "actions": ["hold", "buy", "sell"]},
    "action_settings": {"step_value_cents": 50000},
    "evidence": [{"id": "px-VOLT", "kind": "price_series", "label": "VOLT daily prices", "description": "12 daily closes"}],
}

ALL = {"positive": POSITIVE_CONCENTRATED, "quiet": QUIET_NEUTRAL, "conflicting": CONFLICTING}


def get(name):
    return copy.deepcopy(ALL[name])


# Sample decision facts shaped like what Codex will pass to coach.explain.
# Values are hand-entered stand-ins, not outputs of Codex's simulator.
BLOCKED_FACTS = {
    "scenario_id": "local-positive-concentration",
    "action": "strategy",
    "sentiment_label": "positive",
    "proposal": {"type": "buy", "symbol": "NOVA", "quantity": 4, "reason": "..."},
    "gate": {"status": "blocked", "rule_ids": ["max_position_weight"], "explanation": "NOVA would be 23.7% of the portfolio after costs, above the 20% limit.", "max_position_weight": 0.20},
    "metrics": {"daily_volatility": 0.041, "position_weight_before": 0.1875, "position_weight_proposed": 0.2373, "lookback_days": 11},
    "comparison": {"end_value_if_executed_cents": None, "end_value_if_hold_cents": 994000, "execution_cost_cents": 0, "explanation": "Blocked; no executed outcome."},
}

ALLOWED_FACTS = {
    "scenario_id": "local-quiet-neutral",
    "action": "increase",
    "sentiment_label": "neutral",
    "proposal": {"type": "buy", "symbol": "CALM", "quantity": 10, "reason": "User chose increase."},
    "gate": {"status": "allowed", "rule_ids": [], "explanation": "Within all demo limits.", "max_position_weight": 0.20},
    "metrics": {"daily_volatility": 0.006, "position_weight_before": 0.10, "position_weight_proposed": 0.1497, "lookback_days": 11},
    "comparison": {"end_value_if_executed_cents": 1000250, "end_value_if_hold_cents": 1000400, "execution_cost_cents": 250, "explanation": "Executed."},
}

UNAVAILABLE_FACTS = {
    "scenario_id": "local-quiet-neutral",
    "action": "strategy",
    "proposal": {"type": "hold", "symbol": None, "quantity": 0, "reason": "..."},
    "gate": {"status": "unavailable", "rule_ids": ["insufficient_price_history"], "explanation": "Not enough daily observations to compute volatility.", "max_position_weight": 0.20},
    "metrics": {"daily_volatility": None, "position_weight_before": 0.10, "position_weight_proposed": None, "lookback_days": 11},
    "comparison": {"end_value_if_executed_cents": None, "end_value_if_hold_cents": 1000000, "execution_cost_cents": 0, "explanation": "Unavailable."},
}
