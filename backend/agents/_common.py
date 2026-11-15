"""Shared helpers for the agent modules (owned by Claude).

Everything here is pure: no file I/O, no network, no mutation of inputs.

The observation shape used here is PROVISIONAL. Codex owns
backend/contracts.py and contracts/agents-v1.md; when those land, adjust
`normalize_observation` (the single adapter point) rather than the modules.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

SENTIMENT_LABELS = ("positive", "negative", "neutral", "mixed", "insufficient")
HEADLINE_TONES = ("positive", "negative", "neutral")

# Keys that would carry next-step or future information. The policy-visible
# observation must never contain them; if one appears we drop it and warn so
# Codex can fix the observation builder. Matching is on exact key names.
FORBIDDEN_FUTURE_KEYS = frozenset(
    {
        "outcome",
        "outcomes",
        "next_step",
        "next_step_outcome",
        "next_outcome",
        "next_price",
        "next_price_cents",
        "next_prices",
        "future",
        "future_prices",
        "future_outcome",
        "expected_results",
    }
)

DEFAULT_STEP_FRACTION = 0.05  # fallback sizing when Codex supplies no step setting
DEFAULT_HIGH_VOLATILITY = 0.03  # illustrative daily-volatility threshold for wording only


def plain_copy(value: Any) -> Any:
    """Deep-copy into plain dicts/lists so callers' objects are never touched.

    Accepts MappingProxyType, tuples, frozen dataclass-like mappings, etc.
    """
    if isinstance(value, Mapping):
        return {str(k): plain_copy(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain_copy(v) for v in value]
    if hasattr(value, "__dataclass_fields__"):
        return {k: plain_copy(getattr(value, k)) for k in value.__dataclass_fields__}
    return copy.deepcopy(value)


def strip_future_fields(value: Any, path: str = "observation") -> tuple[Any, list[str]]:
    """Remove forbidden future keys anywhere in the structure. Returns (clean, removed_paths)."""
    removed: list[str] = []
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            sub = f"{path}.{key}"
            if key in FORBIDDEN_FUTURE_KEYS:
                removed.append(sub)
                continue
            clean[key], more = strip_future_fields(item, sub)
            removed.extend(more)
        return clean, removed
    if isinstance(value, list):
        out = []
        for i, item in enumerate(value):
            cleaned, more = strip_future_fields(item, f"{path}[{i}]")
            out.append(cleaned)
            removed.extend(more)
        return out, removed
    return value, removed


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    f = float(value)
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def normalize_observation(observation: Any) -> tuple[dict, list[str]]:
    """Copy, strip future data, and flatten the observation into the fields agents use.

    Returns (normalized, warnings). Never raises on missing fields; missing data is
    represented as None/empty and reported by the caller as a limitation.
    """
    warnings: list[str] = []
    raw = plain_copy(observation) if observation is not None else {}
    if not isinstance(raw, dict):
        return _empty_normalized(), ["Observation was not a mapping; treated as empty."]

    raw, removed = strip_future_fields(raw)
    if removed:
        warnings.append(
            "Observation contained future/outcome fields that agents must not see; "
            f"they were ignored: {', '.join(sorted(removed))}."
        )

    headlines = []
    seen_ids: set[str] = set()
    for item in raw.get("headlines") or []:
        if not isinstance(item, dict):
            continue
        hid, text = item.get("id"), item.get("text")
        if not isinstance(hid, str) or not hid or not isinstance(text, str):
            warnings.append("A headline without a string id/text was ignored.")
            continue
        if hid in seen_ids:
            warnings.append(f"Duplicate headline id {hid!r} ignored.")
            continue
        seen_ids.add(hid)
        headlines.append(
            {
                "id": hid,
                "text": text,
                "published_at": item.get("published_at"),
                "fixture_tone": item.get("fixture_tone"),
            }
        )

    evidence = [e for e in (raw.get("evidence") or []) if isinstance(e, dict) and isinstance(e.get("id"), str)]

    portfolio = raw.get("portfolio") or raw.get("holdings") or {}
    positions = [p for p in (portfolio.get("positions") or []) if isinstance(p, dict)]

    metrics = raw.get("metrics") or {}
    settings = raw.get("action_settings") or {}
    permitted = raw.get("permitted") or {}
    permitted_symbols = [s for s in (permitted.get("symbols") or raw.get("permitted_symbols") or []) if isinstance(s, str)]
    permitted_actions = [a for a in (permitted.get("actions") or raw.get("permitted_actions") or []) if isinstance(a, str)]

    focus = raw.get("focus_symbol") or settings.get("symbol")
    if not isinstance(focus, str) or not focus:
        if len(permitted_symbols) == 1:
            focus = permitted_symbols[0]
        elif positions:
            focus = max(positions, key=lambda p: p.get("value_cents") or 0).get("symbol")
        else:
            focus = None

    fixture_labels = raw.get("fixture_sentiment") or {}
    if not isinstance(fixture_labels, dict):
        fixture_labels = {}

    return (
        {
            "scenario_id": raw.get("scenario_id"),
            "as_of": raw.get("as_of"),
            "headlines": headlines,
            "fixture_labels": fixture_labels,
            "evidence": evidence,
            "cash_cents": portfolio.get("cash_cents"),
            "positions": positions,
            "total_value_cents": portfolio.get("total_value_cents"),
            "metrics": metrics if isinstance(metrics, dict) else {},
            "settings": settings if isinstance(settings, dict) else {},
            "permitted_symbols": permitted_symbols,
            "permitted_actions": permitted_actions,
            "focus_symbol": focus,
            # Contract v1 uses historical_prices_cents (list for the single permitted
            # instrument); a {symbol: [...]} mapping is still accepted for local fixtures.
            "price_history": raw.get("historical_prices_cents") or raw.get("price_history") or {},
            "action_quantity": _positive_int_or_none(permitted.get("action_quantity")),
        },
        warnings,
    )


def _empty_normalized() -> dict:
    return {
        "scenario_id": None,
        "as_of": None,
        "headlines": [],
        "fixture_labels": {},
        "evidence": [],
        "cash_cents": None,
        "positions": [],
        "total_value_cents": None,
        "metrics": {},
        "settings": {},
        "permitted_symbols": [],
        "permitted_actions": [],
        "focus_symbol": None,
        "price_history": {},
        "action_quantity": None,
    }


def _positive_int_or_none(value: Any) -> int | None:
    return value if _is_positive_int(value) else None


def current_price_cents(norm: dict, symbol: str | None) -> int | None:
    """Decision-time price for `symbol`: position price, else last historical observation."""
    if not symbol:
        return None
    for pos in norm["positions"]:
        if pos.get("symbol") == symbol and _is_positive_int(pos.get("price_cents")):
            return pos["price_cents"]
    history = norm["price_history"]
    if isinstance(history, list):
        series = history if (not norm["permitted_symbols"] or symbol in norm["permitted_symbols"]) else None
    else:
        series = history.get(symbol) if isinstance(history, dict) else None
    if isinstance(series, list) and series:
        last = series[-1]
        price = last.get("price_cents") if isinstance(last, dict) else last
        if _is_positive_int(price):
            return price
    return None


def held_quantity(norm: dict, symbol: str | None) -> int:
    for pos in norm["positions"]:
        if pos.get("symbol") == symbol:
            q = pos.get("quantity")
            return q if isinstance(q, int) and not isinstance(q, bool) and q > 0 else 0
    return 0


def metric(norm: dict, name: str) -> float | None:
    return _finite_number(norm["metrics"].get(name))


def evidence_ids_of_kind(norm: dict, *kinds: str) -> list[str]:
    return [e["id"] for e in norm["evidence"] if e.get("kind") in kinds]


def specialist(role: str, summary: str, evidence_ids: Sequence[str], limitations: Sequence[str]) -> dict:
    # De-duplicate while preserving order.
    ids = list(dict.fromkeys(evidence_ids))
    lims = list(dict.fromkeys(limitations))
    return {"role": role, "summary": summary, "evidence_ids": ids, "limitations": lims}


def format_cents(cents: Any) -> str:
    """Display formatting only (no arithmetic on balances): 1234567 -> '$12,345.67'."""
    if isinstance(cents, bool) or not isinstance(cents, int):
        return "unavailable"
    sign = "-" if cents < 0 else ""
    dollars, rem = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{rem:02d}"


def format_fraction(value: Any) -> str:
    f = _finite_number(value)
    if f is None:
        return "unavailable"
    return f"{f * 100:.1f}%"
