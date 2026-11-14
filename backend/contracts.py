"""Frozen v1 wire and internal schemas. All money is integer USD cents."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonnegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]
Ratio = Annotated[float, Field(ge=0, le=1)]
Text = Annotated[str, Field(min_length=1, max_length=4000)]
Action = Literal["strategy", "hold", "increase", "reduce"]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Position(Record):
    symbol: Text
    name: Text
    quantity: NonnegativeInt
    price_cents: PositiveInt
    value_cents: NonnegativeInt

    @model_validator(mode="after")
    def reconcile(self):
        if self.value_cents != self.quantity * self.price_cents:
            raise ValueError("position value must equal quantity times price")
        return self


class Portfolio(Record):
    cash_cents: NonnegativeInt
    positions: list[Position]
    total_value_cents: PositiveInt

    @model_validator(mode="after")
    def reconcile(self):
        if len({p.symbol for p in self.positions}) != len(self.positions):
            raise ValueError("duplicate portfolio symbols")
        if self.total_value_cents != self.cash_cents + sum(p.value_cents for p in self.positions):
            raise ValueError("portfolio total does not reconcile")
        return self


class Headline(Record):
    id: Text
    text: Text
    published_at: Text


class Scenario(Record):
    id: Text
    title: Text
    as_of: Text
    synthetic: Literal[True]
    summary: Text
    headlines: list[Headline]
    initial_portfolio: Portfolio


class Instrument(Record):
    symbol: Text
    name: Text


class ScenarioFixture(Scenario):
    instrument: Instrument
    historical_prices_cents: list[int | None]
    next_price_cents: PositiveInt
    action_quantity: PositiveInt


class ScenarioList(Record):
    schema_version: Literal["1"] = "1"
    scenarios: list[Scenario]


class EvaluateRequest(Record):
    schema_version: Literal["1"]
    scenario_id: Text
    action: Action


class Evidence(Record):
    id: Text
    kind: Literal["headline", "price_series", "portfolio"]
    label: Text
    description: Text


class Specialist(Record):
    role: Literal["sentiment", "risk", "strategy"]
    summary: Text
    evidence_ids: list[Text]
    limitations: list[Text]


class Metrics(Record):
    daily_volatility: Annotated[float, Field(ge=0)] | None
    position_weight_before: Ratio
    position_weight_proposed: Ratio | None
    lookback_days: NonnegativeInt


class Proposal(Record):
    type: Literal["hold", "buy", "sell"]
    symbol: Text | None
    quantity: NonnegativeInt
    reason: Text

    @model_validator(mode="after")
    def action_shape(self):
        if self.type == "hold":
            if self.quantity != 0 or self.symbol is not None:
                raise ValueError("hold requires quantity 0 and symbol null")
        elif self.quantity == 0 or self.symbol is None:
            raise ValueError("buy/sell requires a symbol and positive whole-share quantity")
        return self


class Gate(Record):
    status: Literal["allowed", "blocked", "unavailable"]
    rule_ids: list[Text]
    explanation: Text
    max_position_weight: Literal[0.20] = 0.20


class Comparison(Record):
    end_value_if_executed_cents: NonnegativeInt | None
    end_value_if_hold_cents: NonnegativeInt
    execution_cost_cents: NonnegativeInt
    explanation: Text


class Choice(Record):
    id: Text
    text: Text


class Lesson(Record):
    concept: Text
    explanation: Text
    question: Text
    choices: Annotated[list[Choice], Field(min_length=2, max_length=6)]
    correct_choice_id: Text
    feedback: Text

    @model_validator(mode="after")
    def valid_answer(self):
        ids = [c.id for c in self.choices]
        if len(set(ids)) != len(ids) or self.correct_choice_id not in ids:
            raise ValueError("lesson requires distinct choices and a matching correct choice")
        return self


class DecisionFacts(Record):
    schema_version: Literal["1"] = "1"
    scenario_id: Text
    evaluation_id: Text
    synthetic: Literal[True] = True
    as_of: Text
    analysis_mode: Literal["model", "fixture"]
    policy_mode: Literal["rule_based", "rl"]
    specialists: list[Specialist]
    evidence: list[Evidence]
    metrics: Metrics
    proposal: Proposal
    gate: Gate
    portfolio_before: Portfolio
    portfolio_after_action: Portfolio
    comparison: Comparison
    warnings: list[Text]


class Evaluation(DecisionFacts):
    explanation_mode: Literal["template", "model"]
    lesson: Lesson


class CoachFacts(DecisionFacts):
    """Internal-only decision context; never added to the public response."""
    action: Action
    sentiment_label: Literal["positive", "negative", "neutral", "mixed", "insufficient"]


class PermittedActions(Record):
    symbols: list[Text]
    actions: list[Literal["hold", "buy", "sell"]]
    action_quantity: PositiveInt
    max_position_weight: Literal[0.20] = 0.20
    transaction_cost_cents: NonnegativeInt


class Observation(Record):
    schema_version: Literal["1"] = "1"
    scenario_id: Text
    synthetic: Literal[True] = True
    as_of: Text
    headlines: list[Headline]
    historical_prices_cents: list[int | None]
    portfolio: Portfolio
    metrics: Metrics
    evidence: list[Evidence]
    permitted: PermittedActions


class HeadlineAssessment(Record):
    headline_id: Text
    tone: Literal["positive", "negative", "neutral"]
    source: Literal["fixture_label", "keyword_rules", "model"]


class SentimentResult(Record):
    sentiment_label: Literal["positive", "negative", "neutral", "mixed", "insufficient"]
    headline_assessments: list[HeadlineAssessment]
    specialist: Specialist
    analysis_mode: Literal["model", "fixture"]
    warnings: list[Text]


class StrategyResult(Record):
    proposal: Proposal
    specialist: Specialist
    policy_mode: Literal["rule_based", "rl"]
    warnings: list[Text]


class CoachResult(Record):
    lesson: Lesson
    explanation_mode: Literal["template", "model"]
    warnings: list[Text]
