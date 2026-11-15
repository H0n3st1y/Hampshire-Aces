import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.agents import rl_policy, sentiment, strategy
from backend.agents.tests import fixtures

ARTIFACT = rl_policy.DEFAULT_ARTIFACT


def _observation(name="positive", action_quantity=4):
    obs = fixtures.get(name)
    obs["permitted"]["action_quantity"] = action_quantity
    return obs


def _artifact(q_table):
    return {"format": rl_policy.ARTIFACT_FORMAT, "artifact_id": "test", "actions": list(rl_policy.ACTIONS), "q_table": q_table}


class RLPolicyTests(unittest.TestCase):
    def _propose_with(self, artifact_dict, obs):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a.json"
            path.write_text(json.dumps(artifact_dict), encoding="utf-8")
            with mock.patch.dict(os.environ, {"AGENTS_POLICY": "rl", "AGENTS_RL_ARTIFACT": str(path), "AGENTS_MODEL_ENABLED": "0"}):
                return strategy.propose(obs, sentiment.analyze(obs))

    def _key(self, obs):
        s = sentiment.analyze(obs)
        p = obs["portfolio"]
        return rl_policy.state_key(s["sentiment_label"], obs["metrics"]["daily_volatility"],
                                   obs["metrics"]["position_weight_before"], p["cash_cents"], p["total_value_cents"])

    def test_trained_artifact_yields_rl_mode(self):
        obs = _observation()
        key = self._key(obs)
        r = self._propose_with(_artifact({key: {"q": [0.0, 1.0, -1.0], "visits": [30, 30, 30]}}), obs)
        self.assertEqual(r["policy_mode"], "rl")
        self.assertEqual(r["proposal"], {**r["proposal"], "type": "buy", "symbol": "NOVA", "quantity": 4})
        self.assertIn("risk gate", r["proposal"]["reason"])

    def test_rl_sell_capped_at_holdings(self):
        obs = _observation("conflicting", action_quantity=50)
        key = self._key(obs)
        r = self._propose_with(_artifact({key: {"q": [0.0, -1.0, 1.0], "visits": [30, 30, 30]}}), obs)
        self.assertEqual((r["proposal"]["type"], r["proposal"]["quantity"]), ("sell", 10))

    def test_rl_never_sells_without_holdings(self):
        obs = _observation()
        obs["portfolio"]["positions"][0]["quantity"] = 0
        obs["portfolio"]["positions"][0]["value_cents"] = 0
        obs["metrics"]["position_weight_before"] = 0.0
        key = self._key(obs)
        r = self._propose_with(_artifact({key: {"q": [0.0, -1.0, 5.0], "visits": [30, 30, 30]}}), obs)
        self.assertEqual(r["proposal"]["type"], "hold")
        self.assertEqual(r["proposal"]["quantity"], 0)

    def test_unseen_or_undertrained_state_falls_back(self):
        obs = _observation()
        for table in ({}, {self._key(obs): {"q": [0, 1, 0], "visits": [1, 1, 1]}}):
            r = self._propose_with(_artifact(table), obs)
            self.assertEqual(r["policy_mode"], "rule_based")
            self.assertTrue(any("too little training" in w for w in r["warnings"]))

    def test_bad_artifact_falls_back(self):
        r = self._propose_with({"format": "something_else"}, _observation())
        self.assertEqual(r["policy_mode"], "rule_based")
        self.assertTrue(any("unexpected format" in w for w in r["warnings"]))

    def test_missing_action_quantity_falls_back(self):
        obs = fixtures.get("positive")  # no permitted.action_quantity
        r = self._propose_with(_artifact({}), obs)
        self.assertEqual(r["policy_mode"], "rule_based")

    @unittest.skipUnless(ARTIFACT.exists(), "trained artifact not present")
    def test_shipped_artifact_loads_and_is_well_formed(self):
        art = rl_policy.load_artifact(ARTIFACT)
        self.assertEqual(art["artifact_id"], "q_policy_v1")
        self.assertGreater(len(art["q_table"]), 0)
        for entry in art["q_table"].values():
            self.assertEqual(len(entry["q"]), 3)
            self.assertEqual(len(entry["visits"]), 3)


if __name__ == "__main__":
    unittest.main()
