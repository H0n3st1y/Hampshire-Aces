import copy
import unittest

from backend.agents import coach
from backend.agents.tests import fixtures


def _lesson(facts):
    return coach.explain(copy.deepcopy(facts))


class CoachTests(unittest.TestCase):
    def assertWellFormed(self, result):
        self.assertEqual(result["explanation_mode"], "template")
        lesson = result["lesson"]
        for key in ("concept", "explanation", "question", "choices", "correct_choice_id", "feedback"):
            self.assertIn(key, lesson)
        ids = [c["id"] for c in lesson["choices"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn(lesson["correct_choice_id"], ids)
        self.assertTrue(all(c["text"] for c in lesson["choices"]))

    def test_blocked_concentration(self):
        r = _lesson(fixtures.BLOCKED_FACTS)
        self.assertWellFormed(r)
        text = r["lesson"]["explanation"]
        self.assertEqual(r["lesson"]["concept"], "concentration")
        self.assertIn("blocked", text)
        self.assertIn("max_position_weight", text)
        self.assertIn("no executed outcome", text)
        self.assertIn("$9,940.00", text)  # supplied hold value, display-formatted
        self.assertIn("23.7%", text)  # supplied proposed weight
        self.assertIn("20.0%", text)
        self.assertNotIn("ends at None", text)

    def test_blocked_by_weight_without_rule_hint(self):
        facts = copy.deepcopy(fixtures.BLOCKED_FACTS)
        facts["gate"]["rule_ids"] = ["R7"]
        self.assertEqual(_lesson(facts)["lesson"]["concept"], "concentration")

    def test_blocked_other_rule(self):
        facts = copy.deepcopy(fixtures.BLOCKED_FACTS)
        facts["gate"].update(rule_ids=["insufficient_cash"], explanation="Not enough cash after costs.")
        facts["metrics"]["position_weight_proposed"] = 0.15
        r = _lesson(facts)
        self.assertWellFormed(r)
        self.assertEqual(r["lesson"]["concept"], "trade_constraints")
        self.assertIn("Not enough cash after costs.", r["lesson"]["explanation"])

    def test_allowed_trade_uses_supplied_values(self):
        r = _lesson(fixtures.ALLOWED_FACTS)
        self.assertWellFormed(r)
        text = r["lesson"]["explanation"]
        self.assertEqual(r["lesson"]["concept"], "transaction_costs")
        self.assertIn("allowed", text)
        self.assertIn("$10,002.50", text)
        self.assertIn("$10,004.00", text)
        self.assertIn("$2.50", text)
        self.assertIn("Your choice to increase", text)

    def test_allowed_high_volatility(self):
        facts = copy.deepcopy(fixtures.ALLOWED_FACTS)
        facts["metrics"]["daily_volatility"] = 0.041
        r = _lesson(facts)
        self.assertEqual(r["lesson"]["concept"], "volatility")
        self.assertIn("4.1%", r["lesson"]["question"])

    def test_mixed_sentiment(self):
        facts = copy.deepcopy(fixtures.ALLOWED_FACTS)
        facts["sentiment_label"] = "mixed"
        self.assertEqual(_lesson(facts)["lesson"]["concept"], "conflicting_sentiment")

    def test_allowed_hold(self):
        facts = copy.deepcopy(fixtures.ALLOWED_FACTS)
        facts.update(action="hold", proposal={"type": "hold", "symbol": None, "quantity": 0, "reason": ""})
        facts["comparison"]["end_value_if_executed_cents"] = None
        r = _lesson(facts)
        self.assertWellFormed(r)
        self.assertEqual(r["lesson"]["concept"], "holding")

    def test_unavailable(self):
        r = _lesson(fixtures.UNAVAILABLE_FACTS)
        self.assertWellFormed(r)
        self.assertEqual(r["lesson"]["concept"], "missing_data")
        self.assertIn("Not enough daily observations", r["lesson"]["explanation"])

    def test_incomplete_facts(self):
        for facts in (None, {}, {"gate": {"status": "allowed"}}, {"gate": {"status": "weird"}, "proposal": {}, "comparison": {}}):
            r = coach.explain(facts)
            self.assertWellFormed(r)
            self.assertEqual(r["lesson"]["concept"], "missing_data")
            self.assertTrue(r["warnings"])

    def test_never_claims_execution_when_blocked(self):
        facts = copy.deepcopy(fixtures.BLOCKED_FACTS)
        facts["comparison"]["end_value_if_executed_cents"] = 1234567  # inconsistent input
        text = _lesson(facts)["lesson"]["explanation"]
        self.assertNotIn("$12,345.67", text)

    def test_no_invented_probabilities(self):
        for facts in (fixtures.BLOCKED_FACTS, fixtures.ALLOWED_FACTS, fixtures.UNAVAILABLE_FACTS):
            lesson = _lesson(facts)["lesson"]
            blob = " ".join([lesson["explanation"], lesson["feedback"]]).lower()
            self.assertNotIn("confidence", blob)
            self.assertNotIn("probability", blob)

    def test_does_not_mutate(self):
        facts = copy.deepcopy(fixtures.BLOCKED_FACTS)
        coach.explain(facts)
        self.assertEqual(facts, fixtures.BLOCKED_FACTS)


if __name__ == "__main__":
    unittest.main()
