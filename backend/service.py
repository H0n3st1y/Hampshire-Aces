"""Orchestrate proposals; execution authority belongs exclusively to simulation."""
from copy import deepcopy
from uuid import uuid4

from .contracts import (
    CoachFacts, CoachResult, DecisionFacts, Evaluation, Evidence, Lesson, Observation,
    PermittedActions, Proposal, ScenarioFixture, SentimentResult, Specialist, StrategyResult,
)
from .integration import AgentFailure, AgentRunner, validate_agent_result
from .metrics import calculate_metrics
from .simulation import TRANSACTION_COST_CENTS, simulate


def build_observation(fixture: ScenarioFixture) -> Observation:
    symbol = fixture.instrument.symbol
    evidence = [Evidence(id=h.id, kind="headline", label="Synthetic headline", description=h.text) for h in fixture.headlines]
    evidence.extend([
        Evidence(id=f"prices:{symbol}", kind="price_series", label=f"Synthetic {symbol} daily prices",
                 description=f"Daily closing prices in USD cents, oldest first through the decision time: {fixture.historical_prices_cents}. No future prices are included."),
        Evidence(id="portfolio:initial", kind="portfolio", label="Simulated starting portfolio",
                 description="Fictional cash and whole-share positions valued at decision-time prices. Every comparison restarts here."),
    ])
    return Observation(
        scenario_id=fixture.id, as_of=fixture.as_of, headlines=deepcopy(fixture.headlines),
        historical_prices_cents=deepcopy(fixture.historical_prices_cents),
        portfolio=fixture.initial_portfolio.model_copy(deep=True), metrics=calculate_metrics(fixture), evidence=evidence,
        permitted=PermittedActions(symbols=[symbol], actions=["hold", "buy", "sell"],
                                   action_quantity=fixture.action_quantity, transaction_cost_cents=TRANSACTION_COST_CENTS),
    )


def _hold(reason: str) -> Proposal:
    return Proposal(type="hold", symbol=None, quantity=0, reason=reason)


def _fallback_sentiment(cause: str) -> SentimentResult:
    return SentimentResult(
        sentiment_label="neutral", headline_assessments=[], analysis_mode="fixture",
        specialist=Specialist(role="sentiment", summary="Emergency fallback: no sentiment conclusion is available.",
                              evidence_ids=[], limitations=["Neutral placeholder; no model or headline analysis ran successfully."]),
        warnings=[f"Sentiment emergency fallback: {cause}."],
    )


def _fallback_strategy(cause: str) -> StrategyResult:
    reason = "Emergency fallback: hold because the strategy module could not supply a validated proposal."
    return StrategyResult(proposal=_hold(reason), policy_mode="rule_based",
                          specialist=Specialist(role="strategy", summary=reason, evidence_ids=[],
                                                limitations=["Safety hold placeholder, not a trained policy or an alternative strategy."]),
                          warnings=[f"Strategy emergency fallback: {cause}."])


def _fallback_coach(facts: DecisionFacts, cause: str) -> CoachResult:
    explanation = (
        f"The independent gate recorded '{facts.gate.status}'. {facts.gate.explanation} "
        f"The simulated hold outcome is {facts.comparison.end_value_if_hold_cents / 100:.2f} USD. "
        "Costs and market moves affect simulated outcomes. The 20% concentration limit cannot prevent all losses."
    )
    lesson = Lesson(
        concept="Independent risk controls", explanation=explanation,
        question="What does the simulator's 20% position limit do?",
        choices=[{"id": "a", "text": "Limits concentration when approving a trade; losses can still occur."},
                 {"id": "b", "text": "Guarantees that an approved trade makes money."}],
        correct_choice_id="a", feedback="The gate checks a documented limit independently of proposals. It does not predict or guarantee returns.",
    )
    return CoachResult(lesson=lesson, explanation_mode="template", warnings=[f"Coach emergency fallback: {cause}."])


def _invoke(runner, module, function, args, result_type, role=None, evidence_ids=None):
    # Validate again here so even an injected/test runner cannot bypass the boundary.
    result = runner.invoke(module, function, deepcopy(args), result_type, role=role, evidence_ids=evidence_ids)
    return validate_agent_result(result, result_type, role, evidence_ids)


def evaluate_scenario(fixture: ScenarioFixture, action: str, runner=None) -> Evaluation:
    if action not in {"strategy", "hold", "increase", "reduce"}:
        raise ValueError("unknown action")
    runner = runner or AgentRunner()
    observation = build_observation(fixture)
    ids = [e.id for e in observation.evidence]
    try:
        sentiment = _invoke(runner, "backend.agents.sentiment", "analyze", [observation.model_dump()],
                            SentimentResult, "sentiment", ids)
        headline_ids = {h.id for h in observation.headlines}
        assessed = {a.headline_id for a in sentiment.headline_assessments}
        if assessed != headline_ids:
            raise AgentFailure("sentiment did not assess exactly the supplied headlines")
    except AgentFailure as exc:
        sentiment = _fallback_sentiment(str(exc))
    if action == "strategy":
        try:
            strategy = _invoke(runner, "backend.agents.strategy", "propose",
                               [observation.model_dump(), sentiment.model_dump()], StrategyResult, "strategy", ids)
            if strategy.proposal.symbol is not None and strategy.proposal.symbol not in observation.permitted.symbols:
                raise AgentFailure("strategy proposed an unpermitted symbol")
        except AgentFailure as exc:
            strategy = _fallback_strategy(str(exc))
    else:
        proposal = _hold("User selected a simulated hold comparison.") if action == "hold" else Proposal(
            type="buy" if action == "increase" else "sell", symbol=fixture.instrument.symbol,
            quantity=fixture.action_quantity, reason=f"User selected {action} by {fixture.action_quantity} whole shares.",
        )
        strategy = StrategyResult(proposal=proposal, policy_mode="rule_based", warnings=[],
                                  specialist=Specialist(role="strategy", summary=proposal.reason,
                                                        evidence_ids=["portfolio:initial"],
                                                        limitations=["Explicit user choice; no strategy model selected this proposal."]))
    result = simulate(fixture, strategy.proposal)
    metrics = observation.metrics.model_copy(update={"position_weight_proposed": result.position_weight_proposed})
    limitations = ["Illustrative simulator settings, not personalized investment advice.",
                   "The cap constrains trades and cannot prevent future price losses."]
    warnings = ["Synthetic scenarios and simulated USD only. Every evaluation restarts from the same initial portfolio."]
    if metrics.daily_volatility is None:
        limitations.append("Daily volatility is unavailable: at least three valid consecutive daily prices are required.")
        warnings.append("Required daily price history is missing or invalid; volatility is null, never zero-filled.")
    risk = Specialist(role="risk", summary=result.gate.explanation, evidence_ids=[f"prices:{fixture.instrument.symbol}", "portfolio:initial"],
                      limitations=limitations)
    warnings.extend(sentiment.warnings + strategy.warnings)
    facts = DecisionFacts(
        scenario_id=fixture.id, evaluation_id=str(uuid4()), as_of=fixture.as_of,
        analysis_mode=sentiment.analysis_mode, policy_mode=strategy.policy_mode,
        specialists=[sentiment.specialist, risk, strategy.specialist], evidence=observation.evidence, metrics=metrics,
        proposal=strategy.proposal, gate=result.gate, portfolio_before=fixture.initial_portfolio.model_copy(deep=True),
        portfolio_after_action=result.portfolio_after_action, comparison=result.comparison, warnings=warnings,
    )
    try:
        coach_facts = CoachFacts(**facts.model_dump(), action=action, sentiment_label=sentiment.sentiment_label)
        coach = _invoke(runner, "backend.agents.coach", "explain", [coach_facts.model_dump()], CoachResult)
        if facts.comparison.end_value_if_executed_cents is not None:
            explanation = coach.lesson.explanation.casefold()
            if "no executed outcome" in explanation:
                raise AgentFailure("coach explanation contradicted the recorded outcome")
    except AgentFailure as exc:
        coach = _fallback_coach(facts, str(exc))
    return Evaluation(**{**facts.model_dump(), "warnings": list(dict.fromkeys(warnings + coach.warnings))},
                      explanation_mode=coach.explanation_mode, lesson=coach.lesson)
