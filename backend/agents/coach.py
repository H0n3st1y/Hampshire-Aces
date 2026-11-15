"""Grounded coach: coach.explain(decision_facts).

Template coach (explanation_mode "template"). It explains facts Codex has
already verified: the proposal, the gate's recorded decision, metrics, and the
comparison outcome. It never changes, re-runs, or second-guesses the gate, never
recalculates balances, and never invents confidence numbers or loss odds.
Numbers are only reformatted for display (cents -> dollars, fraction -> percent).
"""

from __future__ import annotations

from ._common import DEFAULT_HIGH_VOLATILITY, format_cents, format_fraction, plain_copy

_CONCENTRATION_HINTS = ("position", "concentration", "weight", "cap")
_REQUIRED = ("gate", "proposal", "comparison")


def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _actor(facts: dict) -> str:
    action = facts.get("action")
    return {
        "strategy": "The strategy's proposal",
        "increase": "Your choice to increase the position",
        "reduce": "Your choice to reduce the position",
        "hold": "Your choice to hold",
    }.get(action, "The proposed action")


def _describe(proposal: dict) -> str:
    if proposal.get("type") in ("buy", "sell") and proposal.get("symbol"):
        qty = proposal.get("quantity")
        noun = "share" if qty == 1 else "shares"
        return f"{proposal['type']} {qty} {noun} of {proposal['symbol']}"
    return "hold, no trade"


def _subject(facts: dict) -> str:
    """e.g. "The strategy's proposal (buy 4 shares of NOVA)"."""
    return f"{_actor(facts)} ({_describe(facts.get('proposal') or {})})"


def _is_concentration_block(gate: dict, metrics: dict) -> bool:
    ids = " ".join(str(r).lower() for r in gate.get("rule_ids") or [])
    if any(h in ids for h in _CONCENTRATION_HINTS):
        return True
    proposed, cap = _num(metrics.get("position_weight_proposed")), _num(gate.get("max_position_weight"))
    return proposed is not None and cap is not None and proposed > cap


def _outcome_sentence(comparison: dict, gate_status: str) -> str:
    hold = format_cents(comparison.get("end_value_if_hold_cents"))
    executed = comparison.get("end_value_if_executed_cents")
    cost = comparison.get("execution_cost_cents")
    if gate_status != "allowed" or executed is None:
        return (
            f"Because nothing was executed there is no executed outcome to show. "
            f"Simply holding would end at {hold}."
        )
    cost_text = f" after {format_cents(cost)} in modeled costs" if isinstance(cost, int) and cost > 0 else ""
    return f"In the simulation the action ends at {format_cents(executed)}{cost_text}, versus {hold} for holding."


def _gate_sentence(gate: dict) -> str:
    rules = ", ".join(str(r) for r in gate.get("rule_ids") or [])
    text = str(gate.get("explanation") or "").strip()
    label = {"allowed": "allowed", "blocked": "blocked", "unavailable": "could not evaluate"}.get(
        gate.get("status"), "recorded"
    )
    sentence = f"The independent risk gate {label} it"
    if rules:
        sentence += f" (rules: {rules})"
    if text:
        sentence += f": {text.rstrip('.')}."
    else:
        sentence += "."
    return sentence


def _lesson(concept, explanation, question, choices, correct, feedback) -> dict:
    return {
        "concept": concept,
        "explanation": explanation,
        "question": question,
        "choices": [{"id": cid, "text": text} for cid, text in choices],
        "correct_choice_id": correct,
        "feedback": feedback,
    }


def _missing_data_lesson(facts: dict, gate: dict) -> dict:
    return _lesson(
        "missing_data",
        f"{_subject(facts)} could not be evaluated. {_gate_sentence(gate)} "
        "The simulator would rather say it cannot decide than guess with missing prices or metrics. "
        "Nothing was executed and the portfolio is unchanged.",
        "Why does the simulator refuse to evaluate a trade when required data is missing?",
        [
            ("a", "Because a decision based on missing prices or statistics could be badly wrong."),
            ("b", "Because the trade was guaranteed to lose money."),
            ("c", "Because holding is always the best choice."),
        ],
        "a",
        "Correct answer: a. Missing data is not the same as zero risk or zero change. "
        "Saying 'unavailable' is more honest than filling the gap with a guess.",
    )


def _concentration_lesson(facts, gate, metrics, comparison) -> dict:
    proposal = facts.get("proposal") or {}
    before = format_fraction(metrics.get("position_weight_before"))
    proposed = metrics.get("position_weight_proposed")
    cap = format_fraction(gate.get("max_position_weight"))
    proposed_text = format_fraction(proposed)
    if _num(proposed) is not None and proposed_text == cap:
        # Rounds to the cap at display precision but is above it once the fee is included.
        proposed_text = f"just over {cap} (the fixed trading fee tips it over)"
    weight_text = (
        f"would have moved this holding from {before} to {proposed_text} of the portfolio after costs"
        if _num(proposed) is not None
        else f"would have increased a holding that is already {before} of the portfolio"
    )
    return _lesson(
        "concentration",
        f"{_subject(facts)} {weight_text}, above the {cap} single-stock "
        f"limit used in this demo. {_gate_sentence(gate)} {_outcome_sentence(comparison, 'blocked')} "
        "The gate's decision stands; positive headlines do not override a risk limit.",
        "Why did the risk gate block this trade?",
        [
            ("a", "The headlines about the company were negative."),
            ("b", f"The trade would have put more than {cap} of the portfolio into a single stock."),
            ("c", "The portfolio did not have any cash."),
        ],
        "b",
        f"Correct answer: b. Concentration means one company's bad day hits the whole portfolio. "
        f"Even when news looks good, the demo keeps any single stock at or below {cap}.",
    )


def _constraint_lesson(facts, gate, comparison) -> dict:
    return _lesson(
        "trade_constraints",
        f"{_subject(facts)} was not carried out. "
        f"{_gate_sentence(gate)} {_outcome_sentence(comparison, 'blocked')} "
        "The simulator does not quietly shrink a blocked trade to make it fit.",
        "What happens to the practice portfolio when the gate blocks a trade?",
        [
            ("a", "The trade is automatically resized until it fits."),
            ("b", "The portfolio stays exactly as it was; no partial trade is made."),
            ("c", "The trade goes through anyway with a warning."),
        ],
        "b",
        "Correct answer: b. A blocked action changes nothing. Hidden resizing would make it hard to "
        "see what was actually decided.",
    )


def _conflict_lesson(facts, gate, comparison) -> dict:
    return _lesson(
        "conflicting_sentiment",
        f"The headlines for this scenario point in different directions. {_subject(facts)} "
        f"was evaluated. {_gate_sentence(gate)} "
        f"{_outcome_sentence(comparison, gate.get('status'))} "
        "When coverage conflicts, the news alone is a weak signal.",
        "When headlines about the same company conflict, what is a careful next step?",
        [
            ("a", "Follow whichever headline sounds most exciting."),
            ("b", "Assume good news always outweighs bad news."),
            ("c", "Treat the news as a weak signal and weigh it with risk, position size, and costs."),
        ],
        "c",
        "Correct answer: c. Conflicting stories mean uncertainty. A smaller or no change, checked "
        "against risk limits, is often more sensible than reacting to one side.",
    )


def _volatility_lesson(facts, gate, metrics, comparison) -> dict:
    vol = format_fraction(metrics.get("daily_volatility"))
    days = metrics.get("lookback_days")
    window = f"over the last {days} daily returns" if isinstance(days, int) else "over the lookback window"
    return _lesson(
        "volatility",
        f"{_subject(facts)} was evaluated. {_gate_sentence(gate)} "
        f"{_outcome_sentence(comparison, gate.get('status'))} Daily price swings were {vol} {window} "
        "(sample standard deviation of daily returns), which is high for this demo.",
        f"What does a daily volatility of {vol} tell you?",
        [
            ("a", f"The price will rise by {vol} tomorrow."),
            ("b", "Daily moves have typically been about that size recently, so results can swing widely."),
            ("c", f"The risk gate predicts a loss of {vol}."),
        ],
        "b",
        "Correct answer: b. Volatility describes how much prices have moved in the past, not which "
        "way they will move next. Higher volatility means a wider range of possible outcomes.",
    )


def _hold_outcome(comparison: dict) -> str:
    """An allowed hold is 'executed' as no trade; state the hold value without implying a block."""
    return f"At the next synthetic price, holding ends at {format_cents(comparison.get('end_value_if_hold_cents'))}."


def _holding_lesson(facts, gate, comparison) -> dict:
    return _lesson(
        "holding",
        f"{_actor(facts) if facts.get('action') != 'strategy' else 'The strategy'} made no trade. "
        f"{_gate_sentence(gate)} {_hold_outcome(comparison)} "
        "Holding avoids trading costs, but the portfolio's value can still change with prices.",
        "Is holding (making no trade) a real investment decision?",
        [
            ("a", "No, holding means nothing can change."),
            ("b", "Yes. It avoids trading costs, but your existing holdings still rise or fall with prices."),
            ("c", "Only if the news is negative."),
        ],
        "b",
        "Correct answer: b. Holding is a choice with its own risk: you keep whatever exposure you "
        "already have.",
    )


def _costs_lesson(facts, gate, comparison) -> dict:
    return _lesson(
        "transaction_costs",
        f"{_subject(facts)} was allowed. {_gate_sentence(gate)} "
        f"{_outcome_sentence(comparison, 'allowed')} "
        "Holding pays no trading cost, so a trade has to beat holding by more than its cost to come out ahead.",
        "In this simulator, what does a trade pay that holding does not?",
        [
            ("a", "A fee to the risk gate."),
            ("b", "A modeled trading cost, which is subtracted from the trade's result."),
            ("c", "Nothing; trading and holding cost the same."),
        ],
        "b",
        "Correct answer: b. Every simulated trade pays the same documented cost assumption. "
        "Costs add up, so frequent trading needs a real reason.",
    )


def explain(decision_facts) -> dict:
    """Return a lesson grounded in verified decision facts.

    Output keys:
      lesson: {concept, explanation, question, choices: [{id, text}], correct_choice_id, feedback}
      explanation_mode: "template"
      warnings: [str]
    """
    facts = plain_copy(decision_facts) if isinstance(decision_facts, dict) else {}
    warnings: list[str] = []
    missing = [k for k in _REQUIRED if not isinstance(facts.get(k), dict)]
    gate = facts.get("gate") if isinstance(facts.get("gate"), dict) else {}
    metrics = facts.get("metrics") if isinstance(facts.get("metrics"), dict) else {}
    comparison = facts.get("comparison") if isinstance(facts.get("comparison"), dict) else {}
    proposal = facts.get("proposal") if isinstance(facts.get("proposal"), dict) else {}
    status = gate.get("status")

    if missing:
        warnings.append(f"Coach received incomplete decision facts (missing: {', '.join(missing)}).")
    if status not in ("allowed", "blocked", "unavailable"):
        if not missing:
            warnings.append("Coach received an unknown gate status; explained it as unavailable.")
        status = "unavailable"

    sentiment = facts.get("sentiment_label")
    vol = _num(metrics.get("daily_volatility"))
    threshold = _num(facts.get("high_volatility_threshold")) or DEFAULT_HIGH_VOLATILITY

    if status == "unavailable" or missing:
        lesson = _missing_data_lesson(facts, gate)
    elif status == "blocked":
        lesson = (
            _concentration_lesson(facts, gate, metrics, comparison)
            if _is_concentration_block(gate, metrics)
            else _constraint_lesson(facts, gate, comparison)
        )
    elif sentiment == "mixed":
        lesson = _conflict_lesson(facts, gate, comparison)
    elif vol is not None and vol >= threshold:
        lesson = _volatility_lesson(facts, gate, metrics, comparison)
    elif proposal.get("type") == "hold" or proposal.get("quantity") == 0:
        lesson = _holding_lesson(facts, gate, comparison)
    else:
        lesson = _costs_lesson(facts, gate, comparison)

    return {"lesson": lesson, "explanation_mode": "template", "warnings": warnings}
