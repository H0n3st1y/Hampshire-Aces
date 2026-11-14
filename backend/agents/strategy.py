"""Strategy specialist: strategy.propose(observation, sentiment_result).

Fixed rule (policy_mode "rule_based"), deliberately naive so learners can see
the independent risk gate do its job:

  positive sentiment  -> buy one sizing step of the focus symbol
  negative sentiment  -> sell one sizing step of the held focus symbol (never more than held)
  mixed / neutral / insufficient / missing inputs -> hold

The rule does NOT check the 20% position cap, cash after costs, or any other
risk limit. Codex's gate decides; this module only proposes. It never executes,
approves, resizes after a block, or recalculates balances.

Sizing: whole shares = step_value_cents // price_cents, where step_value_cents is
taken from observation.action_settings.step_value_cents when Codex supplies it,
else DEFAULT_STEP_FRACTION of the supplied total_value_cents.

An RL policy can be selected later via AGENTS_POLICY=rl; until a trained artifact
is integrated this falls back to the rule and says so. policy_mode is "rl" only
when a real trained artifact produced the proposal.
"""

from __future__ import annotations

import os

from ._common import (
    DEFAULT_HIGH_VOLATILITY,
    DEFAULT_STEP_FRACTION,
    current_price_cents,
    evidence_ids_of_kind,
    format_fraction,
    held_quantity,
    metric,
    normalize_observation,
    plain_copy,
    specialist,
)


def _shares(n: int) -> str:
    return "share" if n == 1 else "shares"


def _hold(reason: str) -> dict:
    return {"type": "hold", "symbol": None, "quantity": 0, "reason": reason}


def _step_value_cents(norm: dict) -> int | None:
    step = norm["settings"].get("step_value_cents")
    if isinstance(step, int) and not isinstance(step, bool) and step > 0:
        return step
    total = norm["total_value_cents"]
    if isinstance(total, int) and not isinstance(total, bool) and total > 0:
        fraction = norm["settings"].get("step_fraction", DEFAULT_STEP_FRACTION)
        if isinstance(fraction, (int, float)) and not isinstance(fraction, bool) and 0 < fraction <= 1:
            return int(total * fraction)
    return None


def _allowed(norm: dict, action: str) -> bool:
    # If Codex supplies no permitted list, assume hold/buy/sell are all available.
    return not norm["permitted_actions"] or action in norm["permitted_actions"]


def _rule_proposal(norm: dict, label: str, limitations: list[str], warnings: list[str]) -> dict:
    symbol = norm["focus_symbol"]
    if label in ("mixed", "neutral", "insufficient"):
        why = {
            "mixed": "headlines conflict",
            "neutral": "headlines are neutral",
            "insufficient": "there are no decision-time headlines",
        }[label]
        return _hold(f"Fixed rule: {why}, so the rule holds and makes no trade.")

    if not symbol:
        warnings.append("No focus symbol could be identified; strategy proposed hold.")
        return _hold("Fixed rule: no tradable symbol was identified, so the rule holds.")
    if norm["permitted_symbols"] and symbol not in norm["permitted_symbols"]:
        warnings.append(f"Focus symbol {symbol} is not permitted; strategy proposed hold.")
        return _hold(f"Fixed rule: {symbol} is not a permitted instrument, so the rule holds.")

    price = current_price_cents(norm, symbol)
    if price is None:
        warnings.append(f"No valid positive decision-time price for {symbol}; strategy proposed hold.")
        return _hold(f"Fixed rule: {symbol} has no valid price, so the rule holds.")

    step = _step_value_cents(norm)
    if step is None:
        warnings.append("No sizing setting or portfolio value was supplied; strategy proposed hold.")
        return _hold("Fixed rule: the trade size could not be determined, so the rule holds.")

    shares = step // price
    if label == "positive":
        if not _allowed(norm, "buy"):
            return _hold("Fixed rule: headlines read positive, but buying is not permitted here, so the rule holds.")
        if shares < 1:
            return _hold(f"Fixed rule: one sizing step is less than one share of {symbol}, so the rule holds.")
        limitations.append(
            "This rule follows positive news without checking concentration or volatility; "
            "the independent risk gate decides whether the trade is allowed."
        )
        return {
            "type": "buy",
            "symbol": symbol,
            "quantity": shares,
            "reason": (
                f"Fixed rule: headlines read positive, so the rule proposes buying {shares} "
                f"{_shares(shares)} of {symbol}, sized by a fixed step. It does not check the position "
                "cap; the risk gate does."
            ),
        }

    # negative
    held = held_quantity(norm, symbol)
    if held == 0:
        return _hold(f"Fixed rule: headlines read negative, but no {symbol} shares are held and shorting is not allowed, so the rule holds.")
    if not _allowed(norm, "sell"):
        return _hold("Fixed rule: headlines read negative, but selling is not permitted here, so the rule holds.")
    qty = min(held, max(shares, 1))
    return {
        "type": "sell",
        "symbol": symbol,
        "quantity": qty,
        "reason": (
            f"Fixed rule: headlines read negative, so the rule proposes selling {qty} of the "
            f"{held} {symbol} {_shares(held)} held, sized by a fixed step."
        ),
    }


def _rl_requested() -> bool:
    return os.environ.get("AGENTS_POLICY", "rule_based").strip().lower() == "rl"


def propose(observation, sentiment_result) -> dict:
    """Return a practice proposal for the strategy choice.

    Output keys:
      proposal: {type: "hold"|"buy"|"sell", symbol: str|None, quantity: int, reason: str}
      specialist: {role: "strategy", summary, evidence_ids, limitations}
      policy_mode: "rule_based" | "rl"
      warnings: [str]
    """
    norm, warnings = normalize_observation(observation)
    sentiment = plain_copy(sentiment_result) if isinstance(sentiment_result, dict) else {}
    limitations = [
        "Fixed educational rule, not a trained or optimized strategy.",
        "Proposals are practice actions in a synthetic simulator, not investment advice.",
    ]

    if _rl_requested():
        warnings.append("RL policy was requested but no trained artifact is integrated; used the fixed rule instead.")

    label = sentiment.get("sentiment_label")
    if label not in ("positive", "negative", "neutral", "mixed", "insufficient"):
        warnings.append("Sentiment result was missing or invalid; strategy treated sentiment as insufficient.")
        label = "insufficient"

    proposal = _rule_proposal(norm, label, limitations, warnings)

    vol = metric(norm, "daily_volatility")
    weight = metric(norm, "position_weight_before")
    threshold = norm["settings"].get("high_volatility_threshold", DEFAULT_HIGH_VOLATILITY)
    context = []
    if vol is None:
        limitations.append("Daily volatility was unavailable, so the rule's context omits price swings.")
    else:
        level = "elevated" if isinstance(threshold, (int, float)) and vol >= threshold else "modest"
        context.append(f"daily volatility {format_fraction(vol)} ({level})")
    if weight is not None:
        context.append(f"current {norm['focus_symbol'] or 'position'} weight {format_fraction(weight)}")

    sentiment_ids = [i for i in (sentiment.get("specialist") or {}).get("evidence_ids", []) if isinstance(i, str)]
    headline_ids = {h["id"] for h in norm["headlines"]}
    sentiment_ids = [i for i in sentiment_ids if i in headline_ids]  # only resolvable IDs
    evidence = sentiment_ids + evidence_ids_of_kind(norm, "price_series", "portfolio")

    action_text = (
        "hold" if proposal["type"] == "hold" else f"{proposal['type']} {proposal['quantity']} {proposal['symbol']}"
    )
    summary = f"Fixed rule proposes: {action_text}. Sentiment input: {label}."
    if context:
        summary += " Context: " + "; ".join(context) + "."

    return {
        "proposal": proposal,
        "specialist": specialist("strategy", summary, evidence, limitations),
        "policy_mode": "rule_based",
        "warnings": warnings,
    }
