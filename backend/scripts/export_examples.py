"""Generate complete, validated frontend samples without invoking optional agents."""
import json
from pathlib import Path

from backend.contracts import CoachFacts, CoachResult, EvaluateRequest, Evaluation, Observation, ScenarioList, SentimentResult, StrategyResult
from backend.fixtures import load_scenarios, public_scenarios
from backend.integration import AgentFailure
from backend.service import evaluate_scenario


class OfflineRunner:
    def invoke(self, *args, **kwargs):
        raise AgentFailure("backend offline mode is enabled")


def main():
    fixtures = load_scenarios()
    destination = Path(__file__).resolve().parents[2] / "contracts" / "examples"
    destination.mkdir(parents=True, exist_ok=True)

    def write(name, data):
        (destination / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    write("scenarios.json", public_scenarios(fixtures).model_dump())
    examples = [
        ("allowed.json", fixtures["quiet_market"], "increase"),
        ("blocked.json", fixtures["momentum_concentration"], "increase"),
        ("unavailable.json", fixtures["quiet_market"].model_copy(update={"historical_prices_cents": []}), "increase"),
        ("hold.json", fixtures["quiet_market"], "hold"),
        ("strategy-offline.json", fixtures["momentum_concentration"], "strategy"),
    ]
    for name, fixture, action in examples:
        data = evaluate_scenario(fixture, action, runner=OfflineRunner()).model_dump()
        data["evaluation_id"] = f"example-{name.removesuffix('.json')}"
        write(name, data)
    write("error-400.json", {"error": {"code": "INVALID_REQUEST", "message": "Unknown synthetic scenario_id."}})
    schema_dir = destination.parent / "schemas"
    schema_dir.mkdir(exist_ok=True)
    for record in [EvaluateRequest, Evaluation, ScenarioList, Observation, SentimentResult, StrategyResult, CoachFacts, CoachResult]:
        (schema_dir / f"{record.__name__}.schema.json").write_text(
            json.dumps(record.model_json_schema(), indent=2) + "\n", encoding="utf-8")
    print(f"Exported catalog, five evaluations, and error example to {destination}")


if __name__ == "__main__":
    main()
