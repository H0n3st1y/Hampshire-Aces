"""Production arithmetic, independent risk gate, and reusable research adapter.

``simulate(fixture, proposal)`` is intentionally the research entry point too:
there is only one implementation of fees, risk decisions and balance changes.
Keep the fixture and returned outcomes outside agent observations.
"""
from dataclasses import dataclass

from pydantic import ValidationError

from backend.contracts import Comparison, Gate, Portfolio, Proposal, ScenarioFixture
from backend.metrics import calculate_metrics

TRANSACTION_COST_CENTS = 100
MAX_POSITION_WEIGHT = 0.20


@dataclass(frozen=True)
class SimulationResult:
    gate: Gate
    portfolio_after_action: Portfolio
    comparison: Comparison
    position_weight_proposed: float | None


def _mark_to_market(portfolio: Portfolio, symbol: str, next_price_cents: int) -> int:
    return portfolio.cash_cents + sum(
        p.quantity * (next_price_cents if p.symbol == symbol else p.price_cents)
        for p in portfolio.positions
    )


def simulate(fixture: ScenarioFixture, proposal: Proposal | dict) -> SimulationResult:
    """Validate and evaluate one whole-share proposal without mutating inputs.

    Missing decision-time history is an unavailable result. Invalid actions are
    blocked. Neither result charges a fee or changes the starting portfolio.
    A corrupt starting portfolio or missing outcome raises ValueError: there is
    no truthful public hold-value response possible for those invalid fixtures.
    """
    try:
        before = Portfolio.model_validate(fixture.initial_portfolio.model_dump())
    except (ValidationError, AttributeError) as exc:
        raise ValueError("Invalid fixture starting portfolio") from exc
    next_price = fixture.next_price_cents
    if type(next_price) is not int or next_price <= 0:
        raise ValueError("Invalid fixture next-step price")
    symbol = fixture.instrument.symbol
    hold_value = _mark_to_market(before, symbol, next_price)

    def rejected(status: str, rule: str, explanation: str, weight: float | None = None):
        return SimulationResult(
            gate=Gate(status=status, rule_ids=[rule], explanation=explanation),
            portfolio_after_action=before.model_copy(deep=True),
            comparison=Comparison(
                end_value_if_executed_cents=None,
                end_value_if_hold_cents=hold_value,
                execution_cost_cents=0,
                explanation="No simulated action executed. The hold comparison uses the synthetic next-step price; the starting holdings and cash are unchanged.",
            ),
            position_weight_proposed=weight,
        )

    try:
        action = Proposal.model_validate(proposal.model_dump() if isinstance(proposal, Proposal) else proposal)
    except (ValidationError, AttributeError, TypeError, ValueError):
        return rejected("blocked", "INVALID_PROPOSAL", "Proposal must be hold with zero shares, or buy/sell a positive whole-share quantity.")

    if action.type != "hold" and action.symbol != symbol:
        return rejected("blocked", "SYMBOL_NOT_ALLOWED", "This scenario permits actions only in its named fictional instrument.")

    position = next((p for p in before.positions if p.symbol == symbol), None)
    if position is None:
        return rejected("unavailable", "MARKET_DATA_INVALID", "The scenario instrument has no current portfolio price.")
    prices = fixture.historical_prices_cents
    if not isinstance(prices, list):
        return rejected("unavailable", "MARKET_DATA_INVALID", "Historical prices must be a consecutive daily price sequence.")
    if len(prices) < 3 or any(price is None for price in prices):
        return rejected("unavailable", "MARKET_DATA_MISSING", "At least three consecutive daily prices are required to calculate sample volatility. Missing values are not replaced with zero.")
    if any(type(price) is not int or price <= 0 for price in prices):
        return rejected("unavailable", "MARKET_DATA_INVALID", "Every historical price must be a positive whole-cent amount.")
    if prices[-1] != position.price_cents:
        return rejected("unavailable", "MARKET_DATA_INVALID", "The final historical price must match the decision-time portfolio price.")
    metrics = calculate_metrics(fixture)
    if metrics.daily_volatility is None:
        return rejected("unavailable", "MARKET_DATA_MISSING", "Required decision-time volatility is unavailable.")

    if action.type == "hold":
        return SimulationResult(
            gate=Gate(status="allowed", rule_ids=["HOLD"], explanation="Hold is valid: no shares trade, no fee is charged, and existing holdings remain unchanged."),
            portfolio_after_action=before.model_copy(deep=True),
            comparison=Comparison(
                end_value_if_executed_cents=hold_value,
                end_value_if_hold_cents=hold_value,
                execution_cost_cents=0,
                explanation="Holding and executing hold are identical. Both use the synthetic next-step price; no transaction cost applies.",
            ),
            position_weight_proposed=metrics.position_weight_before,
        )

    amount = action.quantity * position.price_cents
    if action.type == "buy" and before.cash_cents < amount + TRANSACTION_COST_CENTS:
        return rejected("blocked", "CASH_INSUFFICIENT", "Cash must cover the entire purchase plus the fixed $1.00 simulated transaction cost. Borrowing is not permitted.")
    if action.type == "sell" and action.quantity > position.quantity:
        return rejected("blocked", "HOLDINGS_INSUFFICIENT", "Cannot sell more shares than the portfolio holds. Short selling is not permitted.")

    cash = before.cash_cents + (-amount if action.type == "buy" else amount) - TRANSACTION_COST_CENTS
    if cash < 0:
        return rejected("blocked", "CASH_INSUFFICIENT", "Cash including sale proceeds must cover the fixed $1.00 simulated transaction cost.")
    quantity = position.quantity + (action.quantity if action.type == "buy" else -action.quantity)
    total = before.total_value_cents - TRANSACTION_COST_CENTS
    if total <= 0:
        return rejected("blocked", "CASH_INSUFFICIENT", "The transaction cost must leave a positive portfolio value.")
    proposed_weight = quantity * position.price_cents / total
    new_positions = [
        p.model_copy(update={"quantity": quantity, "value_cents": quantity * p.price_cents})
        if p.symbol == symbol else p.model_copy(deep=True)
        for p in before.positions
    ]
    # Exact integer comparison: no rounded ratios can sneak across the 20% cap.
    if any(p.value_cents * 5 > total for p in new_positions):
        return rejected("blocked", "POSITION_LIMIT", "A single-stock position would exceed 20% of the post-trade portfolio value after the fixed $1.00 cost. The proposal is blocked in full, with no resizing.", proposed_weight)
    after = Portfolio(cash_cents=cash, positions=new_positions, total_value_cents=total)
    return SimulationResult(
        gate=Gate(status="allowed", rule_ids=["ALL_CHECKS_PASSED"], explanation="The full proposal passes independent checks for whole shares, available cash/holdings, valid prices, and the 20% post-cost position cap."),
        portfolio_after_action=after,
        comparison=Comparison(
            end_value_if_executed_cents=_mark_to_market(after, symbol, next_price),
            end_value_if_hold_cents=hold_value,
            execution_cost_cents=TRANSACTION_COST_CENTS,
            explanation="The action and hold portfolios are marked at the same synthetic next-step price. The action includes one fixed $1.00 cost; hold has no cost. This outcome was hidden from the decision-time agents.",
        ),
        position_weight_proposed=proposed_weight,
    )


# Explicit stable adapter name for optional research; it is the same callable.
research_step = simulate
