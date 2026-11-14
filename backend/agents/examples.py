"""Runnable offline examples of the three agent modules.

From the repository root:
    python -m backend.agents.examples

Uses Claude's local synthetic fixtures (not Codex's canonical ones) and
hand-entered sample gate/comparison facts. No network access is needed.
"""

import json

from . import coach, sentiment, strategy
from .tests import fixtures


def main() -> None:
    for name in ("positive", "quiet", "conflicting"):
        obs = fixtures.get(name)
        s = sentiment.analyze(obs)
        p = strategy.propose(obs, s)
        print(f"=== {name}: sentiment ({s['analysis_mode']}) ===")
        print(json.dumps(s, indent=2))
        print(f"=== {name}: strategy ({p['policy_mode']}) ===")
        print(json.dumps(p, indent=2))
    for label, facts in (
        ("blocked", fixtures.BLOCKED_FACTS),
        ("allowed", fixtures.ALLOWED_FACTS),
        ("unavailable", fixtures.UNAVAILABLE_FACTS),
    ):
        print(f"=== coach on sample {label} facts ===")
        print(json.dumps(coach.explain(facts), indent=2))


if __name__ == "__main__":
    main()
