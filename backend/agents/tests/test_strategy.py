import builtins
import unittest
from unittest import mock

from backend.agents import sentiment, strategy
from backend.agents.tests import fixtures

HOLD = {"type": "hold", "symbol": None, "quantity": 0}


def _run(obs, sentiment_result=None):
    s = sentiment_result if sentiment_result is not None else sentiment.analyze(obs)
    return strategy.propose(obs, s)


class StrategyTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict("os.environ", {"AGENTS_MODEL_ENABLED": "0", "AGENTS_POLICY": "rule_based"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def assertHold(self, proposal):
        self.assertEqual({k: proposal[k] for k in HOLD}, HOLD)
        self.assertTrue(proposal["reason"])

    def test_positive_buys_whole_shares(self):
        r = _run(fixtures.get("positive"))
        p = r["proposal"]
        self.assertEqual(r["policy_mode"], "rule_based")
        self.assertEqual(p["type"], "buy")
        self.assertEqual(p["symbol"], "NOVA")
        self.assertEqual(p["quantity"], 50000 // 12500)
        self.assertIsInstance(p["quantity"], int)
        self.assertIn("risk gate", p["reason"])
        self.assertEqual(r["specialist"]["role"], "strategy")
        self.assertIn("px-NOVA", r["specialist"]["evidence_ids"])

    def test_conflicting_holds(self):
        self.assertHold(_run(fixtures.get("conflicting"))["proposal"])

    def test_neutral_holds(self):
        self.assertHold(_run(fixtures.get("quiet"))["proposal"])

    def test_negative_sells_no_more_than_held(self):
        obs = fixtures.get("conflicting")
        neg = {"sentiment_label": "negative", "specialist": {"evidence_ids": ["c2"]}}
        obs["action_settings"]["step_value_cents"] = 10_000_000  # step far larger than holding
        p = _run(obs, neg)["proposal"]
        self.assertEqual(p["type"], "sell")
        self.assertEqual(p["quantity"], 10)

    def test_negative_without_holdings_holds(self):
        obs = fixtures.get("conflicting")
        obs["portfolio"]["positions"] = []
        obs["price_history"] = {"VOLT": [{"price_cents": 15000}]}
        self.assertHold(_run(obs, {"sentiment_label": "negative"})["proposal"])

    def test_invalid_price_holds_with_warning(self):
        for bad in (0, -5, 12.5, None, True):
            obs = fixtures.get("positive")
            obs["portfolio"]["positions"][0]["price_cents"] = bad
            obs.pop("price_history")
            r = _run(obs)
            self.assertHold(r["proposal"])
            self.assertTrue(any("price" in w for w in r["warnings"]), bad)

    def test_step_smaller_than_one_share_holds(self):
        obs = fixtures.get("positive")
        obs["action_settings"]["step_value_cents"] = 100
        self.assertHold(_run(obs)["proposal"])

    def test_default_sizing_when_no_step_setting(self):
        obs = fixtures.get("positive")
        obs["action_settings"] = {}
        p = _run(obs)["proposal"]
        self.assertEqual(p["quantity"], int(1_000_000 * 0.05) // 12500)

    def test_buy_not_permitted_holds(self):
        obs = fixtures.get("positive")
        obs["permitted"]["actions"] = ["hold", "sell"]
        self.assertHold(_run(obs)["proposal"])

    def test_symbol_not_permitted_holds(self):
        obs = fixtures.get("positive")
        obs["permitted"]["symbols"] = ["OTHER"]
        self.assertHold(_run(obs)["proposal"])

    def test_missing_sentiment_holds_with_warning(self):
        r = strategy.propose(fixtures.get("positive"), None)
        self.assertHold(r["proposal"])
        self.assertTrue(r["warnings"])

    def test_missing_volatility_is_a_limitation(self):
        obs = fixtures.get("positive")
        obs["metrics"]["daily_volatility"] = None
        r = _run(obs)
        self.assertTrue(any("volatility was unavailable" in l.lower() for l in r["specialist"]["limitations"]))

    def test_evidence_ids_only_resolvable(self):
        obs = fixtures.get("positive")
        fake = {"sentiment_label": "positive", "specialist": {"evidence_ids": ["h1", "invented-id"]}}
        ids = _run(obs, fake)["specialist"]["evidence_ids"]
        self.assertNotIn("invented-id", ids)
        self.assertIn("h1", ids)

    def test_rl_request_without_artifact_stays_rule_based(self):
        with mock.patch.dict("os.environ", {"AGENTS_POLICY": "rl", "AGENTS_RL_ARTIFACT": "does/not/exist.json"}):
            r = _run(fixtures.get("positive"))
        self.assertEqual(r["policy_mode"], "rule_based")
        self.assertTrue(any("RL policy requested but unavailable" in w for w in r["warnings"]))

    def test_contract_action_quantity_is_used_exactly(self):
        obs = fixtures.get("positive")
        obs["permitted"]["action_quantity"] = 3
        self.assertEqual(_run(obs)["proposal"]["quantity"], 3)

    def test_contract_price_list_is_used(self):
        obs = fixtures.get("positive")
        obs.pop("price_history")
        obs["historical_prices_cents"] = [12000, 12500]
        obs["portfolio"]["positions"] = []
        self.assertEqual(_run(obs)["proposal"]["type"], "buy")

    def test_future_data_cannot_change_proposal(self):
        obs = fixtures.get("positive")
        baseline = _run(obs)["proposal"]
        obs["outcome"] = {"next_price_cents": 1}
        obs["future_prices"] = {"NOVA": [1, 1, 1]}
        r = _run(obs)
        self.assertEqual(r["proposal"], baseline)
        self.assertTrue(any("future/outcome" in w for w in r["warnings"]))

    def test_does_not_mutate_inputs_or_read_files(self):
        obs = fixtures.get("positive")
        s = sentiment.analyze(obs)
        obs_before, s_before = fixtures.get("positive"), sentiment.analyze(fixtures.get("positive"))
        with mock.patch.object(builtins, "open", side_effect=AssertionError("file access")):
            strategy.propose(obs, s)  # rule_based mode reads no files
        self.assertEqual(obs, obs_before)
        self.assertEqual(s, s_before)


if __name__ == "__main__":
    unittest.main()
