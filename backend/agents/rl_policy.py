"""Tabular RL policy: shared state features and artifact inference.

Used by research/rl/train.py (training) and strategy.propose (inference) so the
state definition can never drift between the two. Standard library only; no
training code or research packages are imported here.

The artifact is a JSON Q-table trained on synthetic sequences through Codex's
production simulation adapter (see research/rl/README.md). It estimates
synthetic reward only; it is not a forecast and does not explain "why".
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ACTIONS = ("hold", "buy", "sell")
ARTIFACT_FORMAT = "tabular_q_v1"
DEFAULT_ARTIFACT = Path(__file__).resolve().parents[2] / "research" / "artifacts" / "q_policy_v1.json"
MIN_STATE_VISITS = 20  # below this the table is not trusted for a state


def _bucket(value, edges, labels):
    if value is None:
        return "na"
    for edge, label in zip(edges, labels):
        if value < edge:
            return label
    return labels[-1]


def state_key(sentiment_label: str, daily_volatility, position_weight, cash_cents, total_value_cents) -> str:
    """Discretize decision-time inputs. All inputs come from the observation/sentiment result."""
    vol = _bucket(daily_volatility, (0.015, 0.03), ("low", "mid", "high"))
    weight = _bucket(position_weight, (0.05, 0.12, 0.17), ("none", "small", "medium", "near_cap"))
    cash_ratio = None
    if isinstance(cash_cents, int) and isinstance(total_value_cents, int) and total_value_cents > 0:
        cash_ratio = cash_cents / total_value_cents
    cash = _bucket(cash_ratio, (0.10,), ("low", "ok"))
    return f"{sentiment_label}|vol={vol}|w={weight}|cash={cash}"


def feasible_actions(held_quantity: int, permitted_actions) -> list[str]:
    """Actions the policy may choose. Sell needs a holding (no shorting). The gate still decides."""
    allowed = [a for a in ACTIONS if not permitted_actions or a in permitted_actions]
    if held_quantity <= 0 and "sell" in allowed:
        allowed.remove("sell")
    return allowed or ["hold"]


def artifact_path() -> Path:
    return Path(os.environ.get("AGENTS_RL_ARTIFACT") or DEFAULT_ARTIFACT)


class ArtifactError(Exception):
    pass


def load_artifact(path: Path | None = None) -> dict:
    path = path or artifact_path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"RL artifact could not be loaded ({type(exc).__name__}).") from exc
    if not isinstance(data, dict) or data.get("format") != ARTIFACT_FORMAT or not isinstance(data.get("q_table"), dict):
        raise ArtifactError("RL artifact has an unexpected format.")
    if list(data.get("actions", [])) != list(ACTIONS):
        raise ArtifactError("RL artifact action list does not match this code.")
    return data


def greedy_action(artifact: dict, key: str, feasible: list[str]) -> str | None:
    """Greedy action over feasible actions, or None if the state is untrusted/unseen."""
    entry = artifact["q_table"].get(key)
    if not isinstance(entry, dict):
        return None
    q, visits = entry.get("q"), entry.get("visits")
    if not isinstance(q, list) or len(q) != len(ACTIONS) or not isinstance(visits, list):
        return None
    if sum(visits[ACTIONS.index(a)] for a in feasible) < MIN_STATE_VISITS:
        return None
    # Ties resolve toward the earlier action in ACTIONS (hold first).
    return max(feasible, key=lambda a: (q[ACTIONS.index(a)], -ACTIONS.index(a)))
