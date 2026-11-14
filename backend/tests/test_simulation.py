"""Hand-checked accounting, unavailable data, and independent gate boundaries."""
from copy import deepcopy

import pytest

from backend.contracts import ScenarioFixture
from backend.metrics import calculate_metrics
from backend.simulation import research_step, simulate


def fixture(*, quantity=18, cash=820000, price=10000, next_price=8500, history=None):
    return ScenarioFixture.model_validate({
        "id": "test", "title": "Synthetic test", "as_of": "2026-11-14T12:00:00Z",
        "synthetic": True, "summary": "Fictional prices and simulated money.",
        "headlines": [], "instrument": {"symbol": "ALFA", "name": "Fictional ALFA"},
        "initial_portfolio": {
            "cash_cents": cash,
            "positions": [{"symbol": "ALFA", "name": "Fictional ALFA", "quantity": quantity,
                           "price_cents": price, "value_cents": quantity * price}],
            "total_value_cents": cash + quantity * price,
        },
        "historical_prices_cents": [10000, 10100, 9900, 10400, 9800, price] if history is None else history,
        "next_price_cents": next_price, "action_quantity": 5,
    })


def proposal(kind="buy", quantity=5, symbol="ALFA"):
    return {"type": kind, "quantity": quantity, "symbol": symbol, "reason": "Synthetic test action."}


def test_hand_checked_sell_and_future_mark_to_market():
    result = simulate(fixture(), proposal("sell"))
    assert result.gate.status == "allowed"
    assert result.portfolio_after_action.cash_cents == 869900
    assert result.portfolio_after_action.positions[0].quantity == 13
    assert result.portfolio_after_action.positions[0].value_cents == 130000
    assert result.portfolio_after_action.total_value_cents == 999900
    assert result.comparison.execution_cost_cents == 100
    assert result.comparison.end_value_if_executed_cents == 980400
    assert result.comparison.end_value_if_hold_cents == 973000


def test_hand_checked_buy():
    result = simulate(fixture(quantity=10, cash=900000, next_price=10100), proposal())
    assert result.gate.status == "allowed"
    assert result.portfolio_after_action.cash_cents == 849900
    assert result.portfolio_after_action.positions[0].quantity == 15
    assert result.portfolio_after_action.total_value_cents == 999900
    assert result.comparison.end_value_if_executed_cents == 1001400
    assert result.comparison.end_value_if_hold_cents == 1001000


def test_hold_is_valid_and_free_even_when_starting_over_limit():
    before = fixture(quantity=25, cash=750000)
    result = simulate(before, proposal("hold", 0, None))
    assert result.gate.status == "allowed"
    assert result.portfolio_after_action == before.initial_portfolio
    assert result.comparison.execution_cost_cents == 0
    assert result.comparison.end_value_if_executed_cents == result.comparison.end_value_if_hold_cents


@pytest.mark.parametrize("starting_quantity", [15, 18])
def test_cap_blocks_in_full_including_fee_near_boundary(starting_quantity):
    before = fixture(quantity=starting_quantity, cash=1000000 - starting_quantity * 10000)
    result = simulate(before, proposal())
    assert result.gate.rule_ids == ["POSITION_LIMIT"]
    assert result.gate.status == "blocked"
    assert result.portfolio_after_action == before.initial_portfolio
    assert result.comparison.execution_cost_cents == 0
    assert result.comparison.end_value_if_executed_cents is None


def test_exact_twenty_percent_passes_but_one_cent_less_total_fails():
    # After buying one $100 share, $1 cost leaves $1000 total and $200 stock.
    at_boundary = fixture(quantity=1, cash=90100)
    result = simulate(at_boundary, proposal(quantity=1))
    assert result.gate.status == "allowed"
    assert result.position_weight_proposed == 0.20
    below_total = fixture(quantity=1, cash=90099)
    assert simulate(below_total, proposal(quantity=1)).gate.rule_ids == ["POSITION_LIMIT"]


@pytest.mark.parametrize("raw", [
    proposal(quantity=0), proposal(quantity=-1), proposal(quantity=1.5),
    proposal(quantity=True), proposal(quantity="5"), proposal("hold", 1, None),
    proposal("hold", 0, "ALFA"), proposal("trade"),
    {**proposal(), "approved": True}, {"type": "buy"}, [], None,
])
def test_malformed_proposals_are_independently_blocked(raw):
    before = fixture()
    result = simulate(before, raw)
    assert result.gate.status == "blocked"
    assert result.gate.rule_ids == ["INVALID_PROPOSAL"]
    assert result.portfolio_after_action == before.initial_portfolio
    assert result.comparison.execution_cost_cents == 0
    assert result.comparison.end_value_if_executed_cents is None


def test_unknown_symbol_is_blocked():
    result = simulate(fixture(), proposal(symbol="REAL"))
    assert result.gate.rule_ids == ["SYMBOL_NOT_ALLOWED"]


def test_insufficient_cash_includes_cost():
    result = simulate(fixture(quantity=1, cash=10000), proposal(quantity=1))
    assert result.gate.rule_ids == ["CASH_INSUFFICIENT"]


def test_cannot_oversell():
    result = simulate(fixture(), proposal("sell", 19))
    assert result.gate.rule_ids == ["HOLDINGS_INSUFFICIENT"]


def test_small_sell_must_still_cover_fee_without_borrowing():
    before = fixture(quantity=1, cash=0, price=50, next_price=40, history=[50, 50, 50])
    result = simulate(before, proposal("sell", 1))
    assert result.gate.rule_ids == ["CASH_INSUFFICIENT"]


@pytest.mark.parametrize("history", [[], [10000], [10000, 10000], [10000, None, 10000]])
def test_missing_history_returns_unavailable_not_zero_volatility(history):
    before = fixture(history=history)
    result = simulate(before, proposal())
    assert result.gate.status == "unavailable"
    assert result.gate.rule_ids == ["MARKET_DATA_MISSING"]
    assert result.portfolio_after_action == before.initial_portfolio
    assert result.comparison.end_value_if_executed_cents is None
    assert result.comparison.end_value_if_hold_cents == 973000
    assert calculate_metrics(before).daily_volatility is None


@pytest.mark.parametrize("history", [[10000, 0, 10000], [10000, -1, 10000], [10000, 10000, 9999]])
def test_invalid_price_history_is_unavailable(history):
    before = fixture(history=history)
    result = simulate(before, proposal())
    assert result.gate.status == "unavailable"
    assert result.gate.rule_ids == ["MARKET_DATA_INVALID"]
    assert calculate_metrics(before).daily_volatility is None


@pytest.mark.parametrize("bad_price", [True, float("inf"), float("nan"), 1.2, "10000"])
def test_unsafe_non_integer_history_values_are_rechecked(bad_price):
    before = fixture().model_copy(update={"historical_prices_cents": [10000, bad_price, 10000]})
    assert simulate(before, proposal()).gate.rule_ids == ["MARKET_DATA_INVALID"]
    assert calculate_metrics(before).daily_volatility is None


def test_volatility_uses_sample_daily_returns_without_annualization():
    before = fixture(price=100, history=[100, 110, 100])
    metrics = calculate_metrics(before)
    assert metrics.lookback_days == 2
    # Returns are 1/10 and -1/11; sample std = abs(1/10 + 1/11)/sqrt(2).
    assert metrics.daily_volatility == pytest.approx(0.13499311277197728)
    assert metrics.position_weight_before == 1800 / 821800
    assert metrics.position_weight_proposed is None


def test_flat_prices_are_a_real_zero_not_missing():
    assert calculate_metrics(fixture(history=[10000, 10000, 10000])).daily_volatility == 0.0


def test_repeated_requests_are_stateless_and_do_not_mutate_inputs():
    before, raw = fixture(), proposal("sell")
    snapshot = deepcopy(before.model_dump())
    action_snapshot = deepcopy(raw)
    first, second = simulate(before, raw), simulate(before, raw)
    assert first == second
    assert before.model_dump() == snapshot
    assert raw == action_snapshot
    assert research_step is simulate


def test_all_positions_are_checked_not_only_the_traded_instrument():
    before = fixture(quantity=10, cash=500000)
    raw = before.model_dump()
    raw["initial_portfolio"]["positions"].append({
        "symbol": "OTHER", "name": "Fictional OTHER", "quantity": 40,
        "price_cents": 10000, "value_cents": 400000,
    })
    raw["initial_portfolio"]["total_value_cents"] = 1000000
    result = simulate(ScenarioFixture.model_validate(raw), proposal("sell", 1))
    assert result.gate.rule_ids == ["POSITION_LIMIT"]


def test_corrupt_starting_balances_and_future_outcomes_fail_closed():
    before = fixture()
    invalid = before.initial_portfolio.model_copy(update={"total_value_cents": 12})
    with pytest.raises(ValueError, match="starting portfolio"):
        simulate(before.model_copy(update={"initial_portfolio": invalid}), proposal())
    with pytest.raises(ValueError, match="next-step"):
        simulate(before.model_copy(update={"next_price_cents": 0}), proposal())
