"""Load canonical data; construct the public catalog using an explicit allowlist."""
import json
from datetime import datetime
from pathlib import Path

from .contracts import Scenario, ScenarioFixture, ScenarioList

FIXTURES_PATH = Path(__file__).resolve().parents[1] / "contracts" / "scenarios.json"


def load_scenarios(path: Path = FIXTURES_PATH) -> dict[str, ScenarioFixture]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "1" or set(raw) != {"schema_version", "scenarios"}:
        raise ValueError("unsupported fixture envelope")
    fixtures = [ScenarioFixture.model_validate(item) for item in raw["scenarios"]]
    if len({s.id for s in fixtures}) != len(fixtures):
        raise ValueError("duplicate scenario ids")
    for fixture in fixtures:
        as_of = datetime.fromisoformat(fixture.as_of.replace("Z", "+00:00"))
        if as_of.utcoffset() is None or as_of.utcoffset().total_seconds() != 0:
            raise ValueError("scenario as_of must use UTC")
        ids = [h.id for h in fixture.headlines]
        reserved = {"portfolio:initial", f"prices:{fixture.instrument.symbol}"}
        if len(set(ids)) != len(ids) or set(ids) & reserved:
            raise ValueError("duplicate or reserved headline ids")
        for headline in fixture.headlines:
            published = datetime.fromisoformat(headline.published_at.replace("Z", "+00:00"))
            if published.utcoffset() is None or published > as_of:
                raise ValueError("headlines must be available at decision time")
        matches = [p for p in fixture.initial_portfolio.positions if p.symbol == fixture.instrument.symbol]
        if len(matches) != 1:
            raise ValueError("fixture must provide its instrument's decision-time position/price")
    return {s.id: s for s in fixtures}


def public_scenarios(fixtures: dict[str, ScenarioFixture]) -> ScenarioList:
    return ScenarioList(scenarios=[
        Scenario.model_validate({k: s.model_dump()[k] for k in Scenario.model_fields})
        for s in fixtures.values()
    ])
