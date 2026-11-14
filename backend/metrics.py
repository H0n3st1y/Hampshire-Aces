"""Decision-time statistics; this module never reads a next-step outcome."""
from statistics import stdev

from backend.contracts import Metrics, Portfolio, ScenarioFixture


def calculate_metrics(fixture: ScenarioFixture) -> Metrics:
    """Sample stdev of all supplied consecutive daily simple returns.

    The lookback is the number of daily intervals supplied, not calendar days.
    At least three positive whole-cent price observations (two returns) are
    required. Missing/invalid prices or a stale final price make volatility null.
    No annualization, interpolation, rounding, or zero substitution is applied.
    """
    portfolio = Portfolio.model_validate(fixture.initial_portfolio.model_dump())
    position = next(
        (p for p in portfolio.positions if p.symbol == fixture.instrument.symbol), None
    )
    prices = fixture.historical_prices_cents
    lookback = max(len(prices) - 1, 0) if isinstance(prices, list) else 0
    volatility = None
    if (
        isinstance(prices, list)
        and len(prices) >= 3
        and all(type(price) is int and price > 0 for price in prices)
        and position is not None
        and prices[-1] == position.price_cents
    ):
        returns = [current / prior - 1 for prior, current in zip(prices, prices[1:])]
        volatility = stdev(returns)
    return Metrics(
        daily_volatility=volatility,
        position_weight_before=(position.value_cents / portfolio.total_value_cents if position else 0.0),
        position_weight_proposed=None,
        lookback_days=lookback,
    )
