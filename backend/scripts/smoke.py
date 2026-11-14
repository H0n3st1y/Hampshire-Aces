"""Exercise a running HTTP server. No model credentials or frontend required."""
import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.contracts import Evaluation, ScenarioList


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    def send(path, body=None, method=None, headers=None):
        payload = json.dumps(body).encode() if body is not None else None
        request = Request(args.base_url.rstrip("/") + path, data=payload,
                          headers={"Content-Type": "application/json", **(headers or {})}, method=method)
        with urlopen(request, timeout=40) as response:
            raw = response.read()
            return (json.loads(raw) if raw and response.headers.get_content_type() == "application/json" else None), response.headers

    catalog, _ = send("/api/scenarios")
    ScenarioList.model_validate(catalog)
    assert len(catalog["scenarios"]) == 3
    assert "next_price_cents" not in json.dumps(catalog)
    expected = {
        "momentum_concentration": {"increase": ("blocked", None, 973000), "reduce": ("allowed", 980400, 973000)},
        "quiet_market": {"increase": ("allowed", 1001400, 1001000), "reduce": ("allowed", 1000400, 1001000)},
        "conflicting_signals": {"increase": ("blocked", None, 992500), "reduce": ("allowed", 994900, 992500)},
    }
    for scenario_id in expected:
        for action in ["strategy", "hold", "increase", "reduce"]:
            body = {"schema_version": "1", "scenario_id": scenario_id, "action": action}
            payload, _ = send("/api/evaluate", body)
            result = Evaluation.model_validate(payload)
            if action in expected[scenario_id]:
                status, executed, held = expected[scenario_id][action]
                assert (result.gate.status, result.comparison.end_value_if_executed_cents,
                        result.comparison.end_value_if_hold_cents) == (status, executed, held)
            if result.gate.status != "allowed":
                assert result.portfolio_after_action == result.portfolio_before
                assert result.comparison.end_value_if_executed_cents is None
            for portfolio in [result.portfolio_before, result.portfolio_after_action]:
                assert portfolio.cash_cents + sum(p.value_cents for p in portfolio.positions) == portfolio.total_value_cents
            print(f"{scenario_id}/{action}: {result.proposal.type} {result.proposal.quantity}, {result.gate.status}; "
                  f"modes={result.analysis_mode}/{result.policy_mode}/{result.explanation_mode}")
    request = {"schema_version": "1", "scenario_id": "quiet_market", "action": "increase"}
    first, _ = send("/api/evaluate", request)
    second, _ = send("/api/evaluate", request)
    assert first.pop("evaluation_id") != second.pop("evaluation_id")
    assert first == second
    try:
        send("/api/evaluate", {**request, "action": "invalid"})
        raise AssertionError("malformed action was accepted")
    except HTTPError as error:
        assert error.code == 400
        assert json.load(error)["error"]["code"] == "INVALID_REQUEST"
    _, headers = send("/api/evaluate", method="OPTIONS", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    assert headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    print("HTTP smoke passed: catalog, all 12 paths, repeated requests, malformed action, and local CORS.")


if __name__ == "__main__":
    main()
