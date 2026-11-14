"""Observation privacy and independent gating across the specialist boundary."""
from copy import deepcopy
import json
from pathlib import Path
import multiprocessing
import time

import pytest

from backend.contracts import ScenarioFixture, SentimentResult, StrategyResult
from backend.integration import AgentFailure, AgentRunner, validate_agent_result
from backend.service import build_observation, evaluate_scenario


@pytest.fixture
def fixture():
    path = Path(__file__).resolve().parents[2] / "contracts" / "scenarios.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return ScenarioFixture.model_validate(data["scenarios"][0])


def test_observation_excludes_future_and_is_independent_copy(fixture):
    before = fixture.model_dump()
    first = build_observation(fixture)
    other_outcome = fixture.model_copy(update={"next_price_cents": 12345})
    assert first == build_observation(other_outcome)
    payload = first.model_dump()
    assert set(payload) == {
        "schema_version", "scenario_id", "synthetic", "as_of", "headlines",
        "historical_prices_cents", "portfolio", "metrics", "evidence", "permitted"
    }
    def collect_keys(value):
        if isinstance(value, dict):
            return set(value).union(*(collect_keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(collect_keys(item) for item in value))
        return set()

    keys = collect_keys(payload)
    for key in ("next_price_cents", "comparison", "next_step", "outcome", "lesson"):
        assert key not in keys
    assert payload["metrics"]["position_weight_proposed"] is None
    first.portfolio.positions[0].quantity = 999
    first.headlines.clear()
    first.historical_prices_cents[0] = 1
    assert fixture.model_dump() == before


class RecordingRunner:
    """Known-valid outputs while observing exactly what each specialist receives."""

    def __init__(self, mutate_sentiment=False):
        self.calls = []
        self.mutate_sentiment = mutate_sentiment

    def invoke(self, module_name, function_name, args, result_type, **kwargs):
        self.calls.append((module_name, function_name, deepcopy(args)))
        if function_name == "analyze":
            if self.mutate_sentiment:
                args[0]["portfolio"]["positions"][0]["quantity"] = 999
                args[0]["headlines"].clear()
            result = {
                "sentiment_label": "positive", "headline_assessments": [
                    {"headline_id": h["id"], "tone": "positive", "source": "keyword_rules"}
                    for h in self.calls[-1][2][0]["headlines"]
                ],
                "specialist": {"role": "sentiment", "summary": "Synthetic positive headline reading.",
                               "evidence_ids": [], "limitations": []},
                "analysis_mode": "fixture", "warnings": [],
            }
        elif function_name == "propose":
            result = {
                "proposal": {"type": "buy", "symbol": "ALFA", "quantity": 5,
                             "reason": "Test specialist proposes the full five-share action."},
                "specialist": {"role": "strategy", "summary": "Proposal awaits independent gate.",
                               "evidence_ids": [], "limitations": []},
                "policy_mode": "rule_based", "warnings": [],
            }
        else:
            result = {
                "lesson": {
                    "concept": "Concentration", "explanation": "The independent gate blocked this proposal.",
                    "question": "Which component decides whether a proposal may execute?",
                    "choices": [{"id": "gate", "text": "The independent risk gate"},
                                {"id": "news", "text": "A positive headline"}],
                    "correct_choice_id": "gate", "feedback": "The gate independently validates each proposal.",
                },
                "explanation_mode": "template", "warnings": [],
            }
        return result_type.model_validate(result)


def test_strategy_proposal_cannot_bypass_gate_and_coach_sees_verified_results(fixture):
    runner = RecordingRunner()
    result = evaluate_scenario(fixture, "strategy", runner=runner)
    assert result.proposal.type == "buy"
    assert result.proposal.quantity == 5
    assert result.gate.status == "blocked"
    assert "POSITION_LIMIT" in result.gate.rule_ids
    assert result.portfolio_after_action == result.portfolio_before
    assert result.comparison.end_value_if_executed_cents is None
    for _, function_name, args in runner.calls:
        if function_name in ("analyze", "propose"):
            assert "next_price_cents" not in json.dumps(args)
            assert "comparison" not in args[0]
        elif function_name == "explain":
            assert args[0]["gate"]["status"] == "blocked"
            assert args[0]["comparison"]["end_value_if_executed_cents"] is None
            assert args[0]["portfolio_after_action"] == args[0]["portfolio_before"]
    assert [name for _, name, _ in runner.calls] == ["analyze", "propose", "explain"]


def test_agent_mutations_do_not_change_next_specialist_or_fixture(fixture):
    runner = RecordingRunner(mutate_sentiment=True)
    before = fixture.model_dump()
    result = evaluate_scenario(fixture, "strategy", runner=runner)
    strategy_args = next(args for _, name, args in runner.calls if name == "propose")
    assert strategy_args[0]["portfolio"]["positions"][0]["quantity"] == 18
    assert len(strategy_args[0]["headlines"]) == 2
    assert result.portfolio_before.positions[0].quantity == 18
    assert fixture.model_dump() == before


class FailingRunner:
    def invoke(self, *args, **kwargs):
        raise AgentFailure("unavailable")


def test_all_module_failures_have_labeled_neutral_hold_template_fallback(fixture):
    result = evaluate_scenario(fixture, "strategy", runner=FailingRunner())
    assert result.proposal.type == "hold"
    assert result.analysis_mode == "fixture"
    assert result.policy_mode == "rule_based"
    assert result.explanation_mode == "template"
    assert len(result.warnings) >= 3
    assert result.portfolio_before == result.portfolio_after_action
    assert result.comparison.execution_cost_cents == 0


@pytest.mark.parametrize("history", [[], [10000], [10000, 10000], [10000, None, 10000]])
def test_missing_history_is_unavailable_with_null_metric(fixture, history):
    missing = fixture.model_copy(update={"historical_prices_cents": history}, deep=True)
    result = evaluate_scenario(missing, "increase", runner=FailingRunner())
    assert result.gate.status == "unavailable"
    assert result.metrics.daily_volatility is None
    assert result.comparison.end_value_if_executed_cents is None
    assert result.comparison.end_value_if_hold_cents == 973000
    assert result.portfolio_after_action == result.portfolio_before
    assert result.warnings


@pytest.mark.parametrize("scenario_id,proposal_type,gate_status", [
    ("momentum_concentration", "buy", "blocked"),
    ("quiet_market", "hold", "allowed"),
    ("conflicting_signals", "hold", "allowed"),
])
def test_delivered_claude_proposals_integrate_and_coach_remains_truthful(monkeypatch, scenario_id, proposal_type, gate_status):
    if not (Path(__file__).resolve().parents[1] / "agents" / "coach.py").exists():
        pytest.skip("Claude modules not delivered yet")
    monkeypatch.setenv("AGENT_MODE", "auto")
    monkeypatch.setenv("AGENTS_MODEL_ENABLED", "0")
    monkeypatch.setenv("AGENTS_POLICY", "rule_based")
    path = Path(__file__).resolve().parents[2] / "contracts" / "scenarios.json"
    scenarios = json.loads(path.read_text(encoding="utf-8"))["scenarios"]
    fixture = ScenarioFixture.model_validate(next(s for s in scenarios if s["id"] == scenario_id))
    result = evaluate_scenario(fixture, "strategy")
    assert result.analysis_mode == "fixture"
    assert result.policy_mode == "rule_based"
    assert result.explanation_mode == "template"
    assert result.proposal.type == proposal_type
    assert result.proposal.quantity == (5 if proposal_type == "buy" else 0)
    assert result.gate.status == gate_status
    assert not any("Sentiment emergency fallback" in warning or "Strategy emergency fallback" in warning
                   for warning in result.warnings)
    if result.comparison.end_value_if_executed_cents is not None:
        assert "no executed outcome" not in result.lesson.explanation.casefold()
    if scenario_id == "conflicting_signals":
        assert result.lesson.concept == "conflicting_sentiment"
        assert not any("Coach emergency fallback" in warning for warning in result.warnings)


@pytest.mark.parametrize("action", ["hold", "increase", "reduce", "strategy"])
def test_coach_receives_exact_action_and_validated_sentiment_without_public_schema_change(fixture, action):
    runner = RecordingRunner()
    result = evaluate_scenario(fixture, action, runner=runner)
    coach_facts = next(args[0] for _, name, args in runner.calls if name == "explain")
    assert coach_facts["action"] == action
    assert coach_facts["sentiment_label"] == "positive"
    assert coach_facts["gate"] == result.gate.model_dump()
    assert coach_facts["proposal"] == result.proposal.model_dump()
    assert coach_facts["comparison"] == result.comparison.model_dump()
    assert "action" not in result.model_dump()
    assert "sentiment_label" not in result.model_dump()


class ContradictoryCoachRunner(RecordingRunner):
    def invoke(self, module_name, function_name, args, result_type, **kwargs):
        result = super().invoke(module_name, function_name, args, result_type, **kwargs)
        if function_name == "explain":
            payload = result.model_dump()
            payload["lesson"]["explanation"] = "There is no executed outcome to show."
            return payload
        return result


def test_coach_contradicting_allowed_hold_uses_truthful_template_fallback(fixture):
    result = evaluate_scenario(fixture, "hold", runner=ContradictoryCoachRunner())
    assert result.gate.status == "allowed"
    assert result.comparison.end_value_if_executed_cents == 973000
    assert result.comparison.end_value_if_executed_cents == result.comparison.end_value_if_hold_cents
    assert "no executed outcome" not in result.lesson.explanation.casefold()
    assert "9730.00" in result.lesson.explanation
    assert result.explanation_mode == "template"
    assert any("Coach emergency fallback: coach explanation contradicted the recorded outcome" in warning
               for warning in result.warnings)


def strategy_payload():
    return {
        "proposal": {"type": "buy", "symbol": "ALFA", "quantity": 5, "reason": "Synthetic test proposal."},
        "specialist": {"role": "strategy", "summary": "Synthetic test.", "evidence_ids": ["alfa:expansion"], "limitations": []},
        "policy_mode": "rule_based", "warnings": [],
    }


@pytest.mark.parametrize("quantity", [True, 1.5, "5", -1, 0, float("nan"), float("inf")])
def test_agent_proposals_reject_invalid_share_quantities(quantity):
    payload = strategy_payload()
    payload["proposal"]["quantity"] = quantity
    with pytest.raises(AgentFailure):
        validate_agent_result(payload, StrategyResult, "strategy", ["alfa:expansion"])


@pytest.mark.parametrize("alter", [
    lambda result: result["specialist"].update(role="risk"),
    lambda result: result["specialist"].update(evidence_ids=["fabricated:source"]),
    lambda result: result.update(gate={"status": "allowed"}),
    lambda result: result["proposal"].update(type="hold"),
    lambda result: result.update(policy_mode="trained_magic"),
])
def test_invalid_role_evidence_shape_and_mode_are_rejected(alter):
    payload = strategy_payload()
    alter(payload)
    with pytest.raises(AgentFailure):
        validate_agent_result(payload, StrategyResult, "strategy", ["alfa:expansion"])


class InvalidStrategyRunner(RecordingRunner):
    def __init__(self, alteration):
        super().__init__()
        self.alteration = alteration

    def invoke(self, module_name, function_name, args, result_type, **kwargs):
        if function_name == "propose":
            payload = strategy_payload()
            self.alteration(payload)
            return payload  # service must validate even a custom runner's raw return
        return super().invoke(module_name, function_name, args, result_type, **kwargs)


@pytest.mark.parametrize("alteration", [
    lambda result: result["proposal"].update(quantity=True),
    lambda result: result["proposal"].update(symbol="FAKE"),
    lambda result: result["specialist"].update(evidence_ids=["made_up"]),
    lambda result: result.update(gate={"status": "allowed"}),
])
def test_malformed_strategy_outputs_use_safety_hold(fixture, alteration):
    result = evaluate_scenario(fixture, "strategy", runner=InvalidStrategyRunner(alteration))
    assert result.proposal.type == "hold"
    assert result.portfolio_after_action == result.portfolio_before
    assert result.comparison.execution_cost_cents == 0
    assert any("Strategy emergency fallback" in warning for warning in result.warnings)


def test_process_timeout_is_bounded_and_worker_is_reaped(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "auto")
    before = {process.pid for process in multiprocessing.active_children()}
    started = time.monotonic()
    with pytest.raises(AgentFailure, match="deadline"):
        AgentRunner(timeout_seconds=0.1).invoke("time", "sleep", [60], SentimentResult)
    assert time.monotonic() - started < 2.0
    assert {process.pid for process in multiprocessing.active_children()} <= before


def test_process_import_failure_is_generic_and_contains_no_sensitive_details(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "auto")
    with pytest.raises(AgentFailure) as failure:
        AgentRunner().invoke("missing_synthetic_module_for_test", "analyze", [], SentimentResult)
    assert "missing_synthetic_module_for_test" not in str(failure.value)
    assert "Traceback" not in str(failure.value)


def test_runner_validates_schema_after_child_process_return(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "auto")
    payload = strategy_payload()
    payload["specialist"]["evidence_ids"] = ["unknown"]
    with pytest.raises(AgentFailure, match="schema or evidence"):
        AgentRunner().invoke("builtins", "eval", [repr(payload)], StrategyResult, "strategy", ["alfa:expansion"])


def test_oversized_child_output_is_rejected_without_blocking(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "auto")
    started = time.monotonic()
    with pytest.raises(AgentFailure):
        AgentRunner().invoke("builtins", "str", ["x" * 70000], SentimentResult)
    assert time.monotonic() - started < 4.0


def test_child_exception_details_are_not_exposed(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "auto")
    with pytest.raises(AgentFailure) as failure:
        AgentRunner().invoke("builtins", "int", ["private-test-credential"], SentimentResult)
    assert "private-test-credential" not in str(failure.value)
