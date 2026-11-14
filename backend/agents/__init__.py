"""Agent modules owned by Claude: sentiment, strategy, coach.

Callable interfaces (see README.md in this directory):
    sentiment.analyze(observation)
    strategy.propose(observation, sentiment_result)
    coach.explain(decision_facts)

Importing this package performs no network or file I/O and needs only the
Python standard library.
"""

from . import coach, sentiment, strategy

__all__ = ["coach", "sentiment", "strategy"]
