"""Public contract and stateless request tests, using the explicit offline mode."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from backend.contracts import Evaluation, ScenarioList
from backend.main import app
import backend.main as main_module


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "offline")
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def request_body(scenario="momentum_concentration", action="hold"):
    return {"schema_version": "1", "scenario_id": scenario, "action": action}


def test_scenarios_are_public_and_synthetic(client):
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    payload = response.json()
    ScenarioList.model_validate(payload)
    assert {s["id"] for s in payload["scenarios"]} == {
        "momentum_concentration", "quiet_market", "conflicting_signals"
    }
    for scenario in payload["scenarios"]:
        assert scenario["synthetic"] is True
        assert scenario["initial_portfolio"]["total_value_cents"] == 1_000_000
        assert set(scenario) == {
            "id", "title", "as_of", "synthetic", "summary", "headlines", "initial_portfolio"
        }
    assert "next_price_cents" not in response.text
    assert "historical_prices_cents" not in response.text


@pytest.mark.parametrize("scenario,action,status,executed,held,cost", [
    ("momentum_concentration", "increase", "blocked", None, 973000, 0),
    ("momentum_concentration", "reduce", "allowed", 980400, 973000, 100),
    ("momentum_concentration", "hold", "allowed", 973000, 973000, 0),
    ("momentum_concentration", "strategy", "allowed", 973000, 973000, 0),
    ("quiet_market", "increase", "allowed", 1001400, 1001000, 100),
    ("quiet_market", "reduce", "allowed", 1000400, 1001000, 100),
    ("quiet_market", "hold", "allowed", 1001000, 1001000, 0),
    ("quiet_market", "strategy", "allowed", 1001000, 1001000, 0),
    ("conflicting_signals", "increase", "blocked", None, 992500, 0),
    ("conflicting_signals", "reduce", "allowed", 994900, 992500, 100),
    ("conflicting_signals", "hold", "allowed", 992500, 992500, 0),
    ("conflicting_signals", "strategy", "allowed", 992500, 992500, 0),
])
def test_all_scenario_action_paths(client, scenario, action, status, executed, held, cost):
    response = client.post("/api/evaluate", json=request_body(scenario, action))
    assert response.status_code == 200, response.text
    payload = response.json()
    Evaluation.model_validate(payload)
    assert payload["scenario_id"] == scenario
    assert payload["synthetic"] is True
    assert payload["gate"]["status"] == status
    assert payload["gate"]["max_position_weight"] == 0.20
    assert payload["comparison"]["end_value_if_executed_cents"] == executed
    assert payload["comparison"]["end_value_if_hold_cents"] == held
    assert payload["comparison"]["execution_cost_cents"] == cost
    assert payload["analysis_mode"] == "fixture"
    assert payload["policy_mode"] == "rule_based"
    assert payload["explanation_mode"] == "template"
    assert payload["warnings"], "Offline mode must be disclosed"
    assert {s["role"] for s in payload["specialists"]} == {"sentiment", "risk", "strategy"}
    evidence_ids = {e["id"] for e in payload["evidence"]}
    for specialist in payload["specialists"]:
        assert set(specialist["evidence_ids"]) <= evidence_ids
    if status != "allowed":
        assert payload["portfolio_after_action"] == payload["portfolio_before"]
    else:
        assert payload["portfolio_after_action"]["total_value_cents"] == 1_000_000 - cost


@pytest.mark.parametrize("body", [
    {},
    None,
    [],
    {"schema_version": "1", "scenario_id": "quiet_market"},
    {"schema_version": "2", "scenario_id": "quiet_market", "action": "hold"},
    {"schema_version": 1, "scenario_id": "quiet_market", "action": "hold"},
    {"schema_version": "1", "scenario_id": "unknown", "action": "hold"},
    {"schema_version": "1", "scenario_id": "quiet_market", "action": "buy"},
    {"schema_version": "1", "scenario_id": "quiet_market", "action": "HOLD"},
    {"schema_version": "1", "scenario_id": "quiet_market", "action": True},
    {"schema_version": "1", "scenario_id": "quiet_market", "action": "hold", "quantity": 5},
])
def test_bad_requests_are_400_with_stable_error_shape(client, body):
    response = client.post("/api/evaluate", json=body)
    assert response.status_code == 400
    payload = response.json()
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"code", "message"}
    assert payload["error"]["code"] == "INVALID_REQUEST"
    assert isinstance(payload["error"]["message"], str)


def test_invalid_json_is_400(client):
    response = client.post("/api/evaluate", content='{"schema_version":', headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_repeated_requests_restart_from_same_portfolio(client):
    first = client.post("/api/evaluate", json=request_body("quiet_market", "increase")).json()
    second = client.post("/api/evaluate", json=request_body("quiet_market", "increase")).json()
    assert first["evaluation_id"] != second["evaluation_id"]
    first.pop("evaluation_id")
    second.pop("evaluation_id")
    assert first == second
    assert second["portfolio_before"]["positions"][0]["quantity"] == 10
    assert second["portfolio_after_action"]["positions"][0]["quantity"] == 15
    assert client.get("/api/scenarios").json()["scenarios"][1]["initial_portfolio"]["positions"][0]["quantity"] == 10


def test_concurrent_requests_do_not_accumulate_trades(client):
    def evaluate(_):
        response = client.post("/api/evaluate", json=request_body("quiet_market", "increase"))
        assert response.status_code == 200
        return response.json()

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(evaluate, range(8)))
    assert len({r["evaluation_id"] for r in results}) == 8
    assert {r["portfolio_after_action"]["cash_cents"] for r in results} == {849900}
    assert {r["portfolio_after_action"]["positions"][0]["quantity"] for r in results} == {15}


def test_local_browser_cors(client):
    response = client.options("/api/evaluate", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in response.headers["access-control-allow-methods"]
    denied = client.options("/api/evaluate", headers={
        "Origin": "https://unconfigured.example",
        "Access-Control-Request-Method": "POST",
    })
    assert "access-control-allow-origin" not in denied.headers


def test_known_scenario_missing_history_returns_valid_unavailable_evaluation(client, monkeypatch):
    original = app.state.scenarios["quiet_market"]
    monkeypatch.setitem(app.state.scenarios, "quiet_market", original.model_copy(update={"historical_prices_cents": []}, deep=True))
    response = client.post("/api/evaluate", json=request_body("quiet_market", "increase"))
    assert response.status_code == 200
    payload = response.json()
    Evaluation.model_validate(payload)
    assert payload["gate"]["status"] == "unavailable"
    assert payload["metrics"]["daily_volatility"] is None
    assert payload["comparison"]["end_value_if_executed_cents"] is None
    assert payload["comparison"]["end_value_if_hold_cents"] == 1001000
    assert payload["portfolio_after_action"] == payload["portfolio_before"]


def test_unexpected_failure_returns_generic_500_without_internal_details(client, monkeypatch):
    def failed(*args, **kwargs):
        raise RuntimeError("private-provider-token-123")

    monkeypatch.setattr(main_module, "evaluate_scenario", failed)
    response = client.post("/api/evaluate", json=request_body())
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "private-provider-token" not in response.text
    assert "RuntimeError" not in response.text
